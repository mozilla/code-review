/* -*- Mode: C++; tab-width: 20; indent-tabs-mode: nil; c-basic-offset: 2 -*- */
/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

#include "ClientWebGLContext.h"

#include "ClientWebGLExtensions.h"
#include "HostWebGLContext.h"
#include "mozilla/dom/ToJSValue.h"
#include "mozilla/dom/WebGLContextEvent.h"
#include "mozilla/dom/WorkerCommon.h"
#include "mozilla/EnumeratedRange.h"
#include "mozilla/ipc/Shmem.h"
#include "mozilla/layers/CompositorBridgeChild.h"
#include "mozilla/layers/ImageBridgeChild.h"
#include "mozilla/layers/LayerTransactionChild.h"
#include "mozilla/layers/OOPCanvasRenderer.h"
#include "mozilla/layers/TextureClientSharedSurface.h"
#include "mozilla/Preferences.h"
#include "mozilla/ScopeExit.h"
#include "mozilla/StaticPrefs_webgl.h"
#include "nsContentUtils.h"
#include "nsIGfxInfo.h"
#include "TexUnpackBlob.h"
#include "WebGLMethodDispatcher.h"
#include "WebGLChild.h"
#include "WebGLValidateStrings.h"

namespace mozilla {

webgl::NotLostData::NotLostData(ClientWebGLContext& _context)
    : context(_context) {}
webgl::NotLostData::~NotLostData() = default;

// -

bool webgl::ObjectJS::ValidateForContext(
    const ClientWebGLContext& targetContext, const char* const argName) const {
  if (!IsForContext(targetContext)) {
    targetContext.EnqueueError(
        LOCAL_GL_INVALID_OPERATION,
        "`%s` is from a different (or lost) WebGL context.", argName);
    return false;
  }
  return true;
}

void webgl::ObjectJS::WarnInvalidUse(const ClientWebGLContext& targetContext,
                                     const char* const argName) const {
  if (!ValidateForContext(targetContext, argName)) return;

  const auto errEnum = ErrorOnDeleted();
  targetContext.EnqueueError(errEnum, "Object `%s` is already deleted.",
                             argName);
}

static bool GetJSScalarFromGLType(GLenum type,
                                  js::Scalar::Type* const out_scalarType) {
  switch (type) {
    case LOCAL_GL_BYTE:
      *out_scalarType = js::Scalar::Int8;
      return true;

    case LOCAL_GL_UNSIGNED_BYTE:
      *out_scalarType = js::Scalar::Uint8;
      return true;

    case LOCAL_GL_SHORT:
      *out_scalarType = js::Scalar::Int16;
      return true;

    case LOCAL_GL_HALF_FLOAT:
    case LOCAL_GL_HALF_FLOAT_OES:
    case LOCAL_GL_UNSIGNED_SHORT:
    case LOCAL_GL_UNSIGNED_SHORT_4_4_4_4:
    case LOCAL_GL_UNSIGNED_SHORT_5_5_5_1:
    case LOCAL_GL_UNSIGNED_SHORT_5_6_5:
      *out_scalarType = js::Scalar::Uint16;
      return true;

    case LOCAL_GL_UNSIGNED_INT:
    case LOCAL_GL_UNSIGNED_INT_2_10_10_10_REV:
    case LOCAL_GL_UNSIGNED_INT_5_9_9_9_REV:
    case LOCAL_GL_UNSIGNED_INT_10F_11F_11F_REV:
    case LOCAL_GL_UNSIGNED_INT_24_8:
      *out_scalarType = js::Scalar::Uint32;
      return true;
    case LOCAL_GL_INT:
      *out_scalarType = js::Scalar::Int32;
      return true;

    case LOCAL_GL_FLOAT:
      *out_scalarType = js::Scalar::Float32;
      return true;

    default:
      return false;
  }
}

ClientWebGLContext::ClientWebGLContext(const bool webgl2)
    : mIsWebGL2(webgl2),
      mExtLoseContext(new ClientWebGLExtensionLoseContext(*this)) {}

ClientWebGLContext::~ClientWebGLContext() { RemovePostRefreshObserver(); }

bool ClientWebGLContext::UpdateCompositableHandle(
    LayerTransactionChild* aLayerTransaction, CompositableHandle aHandle) {
  // When running OOP WebGL (i.e. when we have a WebGLChild actor), tell the
  // host about the new compositable.  When running in-process, we don't need to
  // care.
  if (mNotLost->outOfProcess) {
    WEBGL_BRIDGE_LOGI("[%p] Setting CompositableHandle to %" PRIx64, this,
                      aHandle.Value());
    return mNotLost->outOfProcess->mWebGLChild->SendUpdateCompositableHandle(
        aLayerTransaction, aHandle);
  }else {
		// Comment to trigger readability-else-after-return
		const auto x = "aa";
	}
  return true;
}

void ClientWebGLContext::JsWarning(const std::string& utf8) const {
  if (!mCanvasElement) {
    return;
  }
  dom::AutoJSAPI api;
  if (!api.Init(mCanvasElement->OwnerDoc()->GetScopeObject())) {
    return;
  }
  const auto& cx = api.cx();
  JS::WarnUTF8(cx, "%s", utf8.c_str());
}

void AutoJsWarning(const std::string& utf8) {
  const AutoJSContext cx;
  JS::WarnUTF8(cx, "%s", utf8.c_str());
}

// ---------

bool ClientWebGLContext::DispatchEvent(const nsAString& eventName) const {
  const auto kCanBubble = CanBubble::eYes;
  const auto kIsCancelable = Cancelable::eYes;
  bool useDefaultHandler = true;

  if (mCanvasElement) {
    nsContentUtils::DispatchTrustedEvent(
        mCanvasElement->OwnerDoc(), static_cast<nsIContent*>(mCanvasElement),
        eventName, kCanBubble, kIsCancelable, &useDefaultHandler);
  } else if (mOffscreenCanvas) {
    // OffscreenCanvas case
    RefPtr<Event> event = new Event(mOffscreenCanvas, nullptr, nullptr);
    event->InitEvent(eventName, kCanBubble, kIsCancelable);
    event->SetTrusted(true);
    useDefaultHandler = mOffscreenCanvas->DispatchEvent(
        *event, CallerType::System, IgnoreErrors());
  }
  return useDefaultHandler;
}

// -

void ClientWebGLContext::EmulateLoseContext() {
  const FuncScope funcScope(*this, "loseContext");
  if (mLossStatus != webgl::LossStatus::Ready) {
    JsWarning("loseContext: Already lost.");
    if (!mNextError) {
      mNextError = LOCAL_GL_INVALID_OPERATION;
    }
    return;
  }
  OnContextLoss(webgl::ContextLossReason::Manual);
}

void ClientWebGLContext::OnContextLoss(const webgl::ContextLossReason reason) {
  MOZ_ASSERT(NS_IsMainThread());
  JsWarning("WebGL context was lost.");

  if (mNotLost) {
    for (const auto& ext : mNotLost->extensions) {
      if (!ext) continue;
      ext->mContext = nullptr;  // Detach.
    }
    mNotLost = {};  // Lost now!
    mNextError = LOCAL_GL_CONTEXT_LOST_WEBGL;
  }

  switch (reason) {
    case webgl::ContextLossReason::Guilty:
      mLossStatus = webgl::LossStatus::LostForever;
      break;

    case webgl::ContextLossReason::None:
      mLossStatus = webgl::LossStatus::Lost;
      break;

    case webgl::ContextLossReason::Manual:
      mLossStatus = webgl::LossStatus::LostManually;
      break;
  }

  const auto weak = WeakPtr<ClientWebGLContext>(this);
  const auto fnRun = [weak]() {
    const auto strong = RefPtr<ClientWebGLContext>(weak);
    if (!strong) return;
    strong->Event_webglcontextlost();
  };
  already_AddRefed<mozilla::Runnable> runnable =
      NS_NewRunnableFunction("enqueue Event_webglcontextlost", fnRun);
  NS_DispatchToCurrentThread(std::move(runnable));
}
