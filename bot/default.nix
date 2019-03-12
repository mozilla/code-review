{ releng_pkgs
}:

let

  inherit (releng_pkgs.lib) mkTaskclusterHook mkTaskclusterMergeEnv mkTaskclusterMergeRoutes mkPython fromRequirementsFile filterSource ;
  inherit (releng_pkgs.pkgs) writeScript gcc cacert gcc-unwrapped glibc glibcLocales xorg patch nodejs-8_x git python27 python36 coreutils clang_5 zlib shellcheck tzdata;
  inherit (releng_pkgs.pkgs.lib) fileContents concatStringsSep ;
  inherit (releng_pkgs.tools) pypi2nix mercurial;

  nodejs = nodejs-8_x;
  python = import ./requirements.nix { inherit (releng_pkgs) pkgs; };
  project_name = "staticanalysis/bot";

  # Customize gecko environment with Nodejs & Python 3 for linters
  gecko-env = releng_pkgs.gecko-env.overrideDerivation(old : {
    buildPhase = old.buildPhase + ''
      echo "export PATH=${nodejs}/bin:${python36}/bin:\$PATH" >> $out/bin/gecko-env
    '';
 } );


  fullTaskEnv = mergeEnv:
    let
      # Taskcluster support for triggerHook
      tcEnv = mkTaskclusterMergeEnv { env = mergeEnv; };

      # Taskcluster support for pulseMessage
      pulseEnv = {
        "$if" = "firedBy == 'pulseMessage'";
        "then" = {
          "TRY_TASK_ID" = {
            "$eval" = "payload.status.taskId";
          };
          "TRY_TASK_GROUP_ID" = {
            "$eval" = "payload.status.taskGroupId";
          };
          "TRY_RUN_ID" = {
            "$eval" = "payload.runId";
          };
        };
        "else" = {};
      };
    in
      {
        "$merge" = tcEnv."$merge" ++ [ pulseEnv ];
      };


  mkBot = branch:
    let
      cacheKey = "services-" + branch + "-static-analysis-bot";
      secretsKey = "repo:github.com/mozilla-releng/services:branch:" + branch;
      hook = mkTaskclusterHook {
        name = "Static analysis automated tests";
        owner = "babadie@mozilla.com";
        taskImage = self.docker;
        workerType = if branch == "production" then "releng-svc-prod" else "releng-svc";

        # These parameters must stay in sync with src/staticanalysis/frontend/src/store.js MAX_TTL constant
        deadline = "2 hours";
        maxRunTime = 2 * 60 * 60;

        # Trigger through Try ending task pulse message
        bindings = [
          {
            exchange = "exchange/taskcluster-queue/v1/task-completed";
            routingKeyPattern = "route.project.relman.codereview.v1.try_ending";
          }
        ];

        scopes = [
          # Used by taskclusterProxy
          ("secrets:get:" + secretsKey)

          # Send emails to relman
          "notify:email:*"

          # Used by cache
          ("docker-worker:cache:" + cacheKey)

          # Needed to index the task in the TaskCluster index
          ("index:insert-task:project.releng.services.project." + branch + ".static_analysis_bot.*")

          # Needed to download the Android sdks for Infer
          "queue:get-artifact:project/gecko/android-*"
        ];
        cache = {
          "${cacheKey}" = "/cache";
        };
        taskEnv = fullTaskEnv {
          "SSL_CERT_FILE" = "${cacert}/etc/ssl/certs/ca-bundle.crt";
          "APP_CHANNEL" = branch;
          "MOZ_AUTOMATION" = "1";
        };

        taskRoutes = [
          # Latest route
          ("index.project.releng.services.project." + branch + ".static_analysis_bot.latest")
        ];

        taskCapabilities = {};
        taskCommand = [
          "/bin/static-analysis-bot"
          "--taskcluster-secret"
          secretsKey
        ];
        taskArtifacts = {
          "public/results" = {
            path = "/tmp/results";
            type = "directory";
          };
        };
      };
    in
      releng_pkgs.pkgs.writeText "taskcluster-hook-${self.name}.json" (builtins.toJSON hook);

  includes = concatStringsSep ":" [
    "${gcc-unwrapped}/include/c++/${gcc-unwrapped.version}"
    "${gcc-unwrapped}/include/c++/${gcc-unwrapped.version}/backward"
    "${gcc-unwrapped}/include/c++/${gcc-unwrapped.version}/x86_64-unknown-linux-gnu"
    "${glibc.dev}/include/"
    "${xorg.libX11.dev}/include"
    "${xorg.xproto}/include"
    "${xorg.libXrender.dev}/include"
    "${xorg.renderproto}/include"
  ];

  self = mkPython {
    inherit python project_name;
    version = fileContents ./VERSION;
    src = filterSource ./. { inherit(self) name; };
    buildInputs =
      [ mercurial clang_5 ] ++
      (fromRequirementsFile ./../../../lib/cli_common/requirements-dev.txt python.packages) ++
      (fromRequirementsFile ./requirements-dev.txt python.packages);
    propagatedBuildInputs =
      [
        # Needed for the static analysis
        glibc
        gcc
        patch
        shellcheck
        tzdata

        # Needed for linters
        nodejs

        # Gecko environment
        gecko-env
      ] ++
      (fromRequirementsFile ./requirements.txt python.packages);
    postInstall = ''
      mkdir -p $out/etc
      mkdir -p $out/tmp
      mkdir -p $out/bin
      mkdir -p $out/usr/bin $out/usr/share
      mkdir -p $out/lib64
      ln -s ${mercurial}/bin/hg $out/bin
      ln -s ${patch}/bin/patch $out/bin

      # Mozlint deps
      ln -s ${gcc}/bin/gcc $out/bin
      ln -s ${nodejs}/bin/node $out/bin
      ln -s ${nodejs}/bin/npm $out/bin
      ln -s ${git}/bin/git $out/bin
      ln -s ${python27}/bin/python2.7 $out/bin/python2.7
      ln -s ${python27}/bin/python2.7 $out/bin/python2
      ln -s ${python36}/bin/python3.6 $out/bin/python3.6
      ln -s ${python36}/bin/python3.6 $out/bin/python3
      ln -s ${coreutils}/bin/env $out/usr/bin/env
      ln -s ${coreutils}/bin/ld $out/bin
      ln -s ${coreutils}/bin/as $out/bin

      # Add program interpreter needed to run clang Taskcluster static build
      # Found this info by using "readelf -l"
      ln -s ${glibc}/lib/ld-linux-x86-64.so.2 $out/lib64

      # Expose gecko env in final output
      ln -s ${gecko-env}/bin/gecko-env $out/bin

      # Use UTC as timezone
      ln -s ${tzdata}/share/zoneinfo/UTC $out/etc/localtime
      ln -s ${tzdata}/share/zoneinfo $out/usr/share
      echo UTC > $out/etc/timezone
    '';
    shellHook = ''
      export PATH="${mercurial}/bin:${git}/bin:${python27}/bin:${python36}/bin:${nodejs}/bin:$PATH"

      # Setup mach automation
      export MOZ_AUTOMATION=1

      # Use clang mozconfig from gecko-env
      export MOZCONFIG=${gecko-env}/conf/mozconfig

      # Use common mozilla state directory
      export MOZBUILD_STATE_PATH=/tmp/mozilla-state

      # Extras for clang-tidy
      export CPLUS_INCLUDE_PATH=${includes}
      export C_INCLUDE_PATH=${includes}

      # Export linters tools
      export CODESPELL=${python.packages.codespell}/bin/codespell
      export SHELLCHECK=${shellcheck}/bin/shellcheck

      # Needed to run clang Taskcluster static build
      # in developers shell
      export LD_LIBRARY_PATH=${zlib}/lib:${gcc-unwrapped.lib}/lib
    '';

    dockerEnv =
      [ "CPLUS_INCLUDE_PATH=${includes}"
        "C_INCLUDE_PATH=${includes}"
        "MOZCONFIG=${gecko-env}/conf/mozconfig"
        "CODESPELL=${python.packages.codespell}/bin/codespell"
        "SHELLCHECK=${shellcheck}/bin/shellcheck"
        "MOZ_AUTOMATION=1"
        "MOZBUILD_STATE_PATH=/tmp/mozilla-state"
        "_JAVA_OPTIONS=-Duser.home=/tmp/mozilla-state"
        "SHELL=xterm"

        # Needed to run clang Taskcluster static build
        # only on built docker image from scratch
        "LD_LIBRARY_PATH=${zlib}/lib:${gcc-unwrapped.lib}/lib"
      ];
    dockerCmd = [];

    passthru = {
      deploy = {
        testing = mkBot "testing";
        staging = mkBot "staging";
        production = mkBot "production";
      };
      update = writeScript "update-${self.name}" ''
        pushd ${self.src_path}
        cache_dir=$PWD/../../../tmp/pypi2nix
        mkdir -p $cache_dir
        eval ${pypi2nix}/bin/pypi2nix -v \
          -C $cache_dir \
          -V 3.7 \
          -O ../../../nix/requirements_override.nix \
          -E libffi \
          -E openssl \
          -E pkgconfig \
          -E freetype.dev \
          -s intreehooks \
          -s flit \
          -s pytest-runner \
          -s setuptools-scm \
          -r requirements.txt \
          -r requirements-dev.txt
        popd
      '';
    };
  };

in self
