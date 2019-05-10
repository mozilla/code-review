{ releng_pkgs
}:

let

  inherit (releng_pkgs.lib) mkTaskclusterHook mkTaskclusterMergeEnv mkTaskclusterMergeRoutes mkPython fromRequirementsFile filterSource ;
  inherit (releng_pkgs.pkgs) writeScript cacert;
  inherit (releng_pkgs.pkgs.lib) fileContents concatStringsSep ;
  inherit (releng_pkgs.tools) pypi2nix;

  python = import ./requirements.nix { inherit (releng_pkgs) pkgs; };
  project_name = "staticanalysis/bot";

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

          # Needed to index the task in the TaskCluster index
          ("index:insert-task:project.releng.services.project." + branch + ".static_analysis_bot.*")
          ("index:insert-task:project.releng.services.tasks.*")

          # Needed to download the Android sdks for Infer
          "queue:get-artifact:project/gecko/android-*"
        ];
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

  self = mkPython {
    inherit python project_name;
    version = fileContents ./VERSION;
    src = filterSource ./. { inherit(self) name; };
    buildInputs =
      (fromRequirementsFile ./../../../lib/cli_common/requirements-dev.txt python.packages) ++
      (fromRequirementsFile ./requirements-dev.txt python.packages);
    propagatedBuildInputs =
      (fromRequirementsFile ./requirements.txt python.packages);
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
