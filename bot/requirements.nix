# generated using pypi2nix tool (version: 2.0.0)
# See more at: https://github.com/garbas/pypi2nix
#
# COMMAND:
#   pypi2nix -v -C /tmp/release-services-w6ozq9ky/src/staticanalysis/bot/../../../tmp/pypi2nix -V 3.7 -O ../../../nix/requirements_override.nix -E libffi -E openssl -E pkgconfig -E freetype.dev -s intreehooks -s flit -s pytest-runner -s setuptools-scm -r requirements.txt -r requirements-dev.txt
#

{ pkgs ? import <nixpkgs> {},
  overrides ? ({ pkgs, python }: self: super: {})
}:

let

  inherit (pkgs) makeWrapper;
  inherit (pkgs.stdenv.lib) fix' extends inNixShell;

  pythonPackages =
  import "${toString pkgs.path}/pkgs/top-level/python-packages.nix" {
    inherit pkgs;
    inherit (pkgs) stdenv;
    python = pkgs.python37;
    # patching pip so it does not try to remove files when running nix-shell
    overrides =
      self: super: {
        bootstrapped-pip = super.bootstrapped-pip.overrideDerivation (old: {
          patchPhase = old.patchPhase + ''
            if [ -e $out/${pkgs.python37.sitePackages}/pip/req/req_install.py ]; then
              sed -i \
                -e "s|paths_to_remove.remove(auto_confirm)|#paths_to_remove.remove(auto_confirm)|"  \
                -e "s|self.uninstalled = paths_to_remove|#self.uninstalled = paths_to_remove|"  \
                $out/${pkgs.python37.sitePackages}/pip/req/req_install.py
            fi
          '';
        });
      };
  };

  commonBuildInputs = with pkgs; [ libffi openssl pkgconfig freetype.dev ];
  commonDoCheck = false;

  withPackages = pkgs':
    let
      pkgs = builtins.removeAttrs pkgs' ["__unfix__"];
      interpreterWithPackages = selectPkgsFn: pythonPackages.buildPythonPackage {
        name = "python37-interpreter";
        buildInputs = [ makeWrapper ] ++ (selectPkgsFn pkgs);
        buildCommand = ''
          mkdir -p $out/bin
          ln -s ${pythonPackages.python.interpreter} \
              $out/bin/${pythonPackages.python.executable}
          for dep in ${builtins.concatStringsSep " "
              (selectPkgsFn pkgs)}; do
            if [ -d "$dep/bin" ]; then
              for prog in "$dep/bin/"*; do
                if [ -x "$prog" ] && [ -f "$prog" ]; then
                  ln -s $prog $out/bin/`basename $prog`
                fi
              done
            fi
          done
          for prog in "$out/bin/"*; do
            wrapProgram "$prog" --prefix PYTHONPATH : "$PYTHONPATH"
          done
          pushd $out/bin
          ln -s ${pythonPackages.python.executable} python
          ln -s ${pythonPackages.python.executable} \
              python3
          popd
        '';
        passthru.interpreter = pythonPackages.python;
      };

      interpreter = interpreterWithPackages builtins.attrValues;
    in {
      __old = pythonPackages;
      inherit interpreter;
      inherit interpreterWithPackages;
      mkDerivation = pythonPackages.buildPythonPackage;
      packages = pkgs;
      overrideDerivation = drv: f:
        pythonPackages.buildPythonPackage (
          drv.drvAttrs // f drv.drvAttrs // { meta = drv.meta; }
        );
      withPackages = pkgs'':
        withPackages (pkgs // pkgs'');
    };

  python = withPackages {};

  generated = self: {
    "Click" = python.mkDerivation {
      name = "Click-7.0";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/f8/5c/f60e9d8a1e77005f664b76ff8aeaee5bc05d0a91798afd7f53fc998dbc47/Click-7.0.tar.gz";
        sha256 = "5b94b49521f6456670fdb30cd82a4eca9412788a93fa6dd6df72c94d5a8ff2d7";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://palletsprojects.com/p/click/";
        license = licenses.bsdOriginal;
        description = "Composable command line interface toolkit";
      };
    };

    "Logbook" = python.mkDerivation {
      name = "Logbook-1.4.3";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/f6/83/20fc0270614919cb799f76e32cf143a54c58ce2fa45c19fd38ac2e4f9977/Logbook-1.4.3.tar.gz";
        sha256 = "a5a96792abd8172c80d61b7530e134524f20e2841981038031e602ed5920fef5";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [
        self."pytest"
        self."pytest-cov"
      ];
      meta = with pkgs.stdenv.lib; {
        homepage = "http://logbook.pocoo.org/";
        license = licenses.bsdOriginal;
        description = "A logging replacement for Python";
      };
    };

    "PyYAML" = python.mkDerivation {
      name = "PyYAML-3.13";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/9e/a3/1d13970c3f36777c583f136c136f804d70f500168edc1edea6daa7200769/PyYAML-3.13.tar.gz";
        sha256 = "3ef3092145e9b70e3ddd2c7ad59bdd0252a94dfe3949721633e41344de00a6bf";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "http://pyyaml.org/wiki/PyYAML";
        license = licenses.mit;
        description = "YAML parser and emitter for Python";
      };
    };

    "Pygments" = python.mkDerivation {
      name = "Pygments-2.3.1";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/64/69/413708eaf3a64a6abb8972644e0f20891a55e621c6759e2c3f3891e05d63/Pygments-2.3.1.tar.gz";
        sha256 = "5ffada19f6203563680669ee7f53b64dabbeb100eb51b61996085e99c03b284a";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "http://pygments.org/";
        license = licenses.bsdOriginal;
        description = "Pygments is a syntax highlighting package written in Python.";
      };
    };

    "RBTools" = python.mkDerivation {
      name = "RBTools-1.0.1";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/80/ce/eb5f57b6d5bd66733c2cd18ef477befd52a067e56c587a5d4d499c09b408/RBTools-1.0.1.tar.gz";
        sha256 = "3b5e70c6936441521dd080e406e85d360bcc802a92d599eac2de2f20305a93d7";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [
        self."backports.shutil-get-terminal-size"
        self."colorama"
        self."six"
        self."texttable"
        self."tqdm"
      ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://www.reviewboard.org/downloads/rbtools/";
        license = licenses.mit;
        description = "Command line tools and API for working with code and document reviews on Review Board";
      };
    };

    "aioamqp" = python.mkDerivation {
      name = "aioamqp-0.12.0";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/51/15/11ceb44c67a5fdd8cc19dddc1bef7d824100ea7488382eee3b4c3331f890/aioamqp-0.12.0.tar.gz";
        sha256 = "80897483fddbae0557e5e9917f52bf4508dfe707f8c979285e0165a9a4a1799f";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/polyconseil/aioamqp";
        license = licenses.bsdOriginal;
        description = "AMQP implementation using asyncio";
      };
    };

    "aiohttp" = python.mkDerivation {
      name = "aiohttp-3.5.4";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/0f/58/c8b83f999da3b13e66249ea32f325be923791c0c10aee6cf16002a3effc1/aiohttp-3.5.4.tar.gz";
        sha256 = "9c4c83f4fa1938377da32bc2d59379025ceeee8e24b89f72fcbccd8ca22dc9bf";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [
        self."async-timeout"
        self."attrs"
        self."chardet"
        self."multidict"
        self."yarl"
      ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/aio-libs/aiohttp";
        license = licenses.asl20;
        description = "Async http client/server framework (asyncio)";
      };
    };

    "async-timeout" = python.mkDerivation {
      name = "async-timeout-3.0.1";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/a1/78/aae1545aba6e87e23ecab8d212b58bb70e72164b67eb090b81bb17ad38e3/async-timeout-3.0.1.tar.gz";
        sha256 = "0c3c816a028d47f659d6ff5c745cb2acf1f966da1fe5c19c77a70282b25f4c5f";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/aio-libs/async_timeout/";
        license = licenses.asl20;
        description = "Timeout context manager for asyncio programs";
      };
    };

    "atomicwrites" = python.mkDerivation {
      name = "atomicwrites-1.3.0";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/ec/0f/cd484ac8820fed363b374af30049adc8fd13065720fd4f4c6be8a2309da7/atomicwrites-1.3.0.tar.gz";
        sha256 = "75a9445bac02d8d058d5e1fe689654ba5a6556a1dfd8ce6ec55a0ed79866cfa6";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/untitaker/python-atomicwrites";
        license = licenses.mit;
        description = "Atomic file writes.";
      };
    };

    "attrs" = python.mkDerivation {
      name = "attrs-18.2.0";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/0f/9e/26b1d194aab960063b266170e53c39f73ea0d0d3f5ce23313e0ec8ee9bdf/attrs-18.2.0.tar.gz";
        sha256 = "10cbf6e27dbce8c30807caf056c8eb50917e0eaafe86347671b57254006c3e69";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://www.attrs.org/";
        license = licenses.mit;
        description = "Classes Without Boilerplate";
      };
    };

    "backports.shutil-get-terminal-size" = python.mkDerivation {
      name = "backports.shutil-get-terminal-size-1.0.0";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/ec/9c/368086faa9c016efce5da3e0e13ba392c9db79e3ab740b763fe28620b18b/backports.shutil_get_terminal_size-1.0.0.tar.gz";
        sha256 = "713e7a8228ae80341c70586d1cc0a8caa5207346927e23d09dcbcaf18eadec80";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/chrippa/backports.shutil_get_terminal_size";
        license = licenses.mit;
        description = "A backport of the get_terminal_size function from Python 3.3's shutil.";
      };
    };

    "boto3" = python.mkDerivation {
      name = "boto3-1.9.96";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/4b/16/e3201b3bf3985c27bc526116fec6be9ac068b9eae4d8717d1301f319b708/boto3-1.9.96.tar.gz";
        sha256 = "c103241394d396ee08548b03d5d1f0f89a7ad1dfa7ccca88a47131f329cca093";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [
        self."botocore"
        self."jmespath"
        self."s3transfer"
      ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/boto/boto3";
        license = licenses.asl20;
        description = "The AWS SDK for Python";
      };
    };

    "botocore" = python.mkDerivation {
      name = "botocore-1.12.96";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/73/04/121bebe0a97f0d4f2ce84b9cb68cdfd572b6abe6753b04ed80b4cddc58a9/botocore-1.12.96.tar.gz";
        sha256 = "55c1594041e6716847d5a8b38181e3cc44e245edbf4598ae2b99e3040073b2cf";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [
        self."docutils"
        self."jmespath"
        self."python-dateutil"
        self."urllib3"
      ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/boto/botocore";
        license = licenses.asl20;
        description = "Low-level, data-driven core of boto 3.";
      };
    };

    "certifi" = python.mkDerivation {
      name = "certifi-2018.11.29";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/55/54/3ce77783acba5979ce16674fc98b1920d00b01d337cfaaf5db22543505ed/certifi-2018.11.29.tar.gz";
        sha256 = "47f9c83ef4c0c621eaef743f133f09fa8a74a9b75f037e8624f83bd1b6626cb7";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://certifi.io/";
        license = licenses.mpl20;
        description = "Python package for providing Mozilla's CA Bundle.";
      };
    };

    "chardet" = python.mkDerivation {
      name = "chardet-3.0.4";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/fc/bb/a5768c230f9ddb03acc9ef3f0d4a3cf93462473795d18e9535498c8f929d/chardet-3.0.4.tar.gz";
        sha256 = "84ab92ed1c4d4f16916e05906b6b75a6c0fb5db821cc65e70cbd64a3e2a5eaae";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/chardet/chardet";
        license = licenses.lgpl3;
        description = "Universal encoding detector for Python 2 and 3";
      };
    };

    "codecov" = python.mkDerivation {
      name = "codecov-2.0.15";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/77/f2/9790ee0f04eb0571841aff5ba1709c7869e82aa2145a04a3d4770807ff50/codecov-2.0.15.tar.gz";
        sha256 = "8ed8b7c6791010d359baed66f84f061bba5bd41174bf324c31311e8737602788";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [
        self."coverage"
        self."requests"
      ];
      meta = with pkgs.stdenv.lib; {
        homepage = "http://github.com/codecov/codecov-python";
        license = "http://www.apache.org/licenses/LICENSE-2.0";
        description = "Hosted coverage reports for Github, Bitbucket and Gitlab";
      };
    };

    "codespell" = python.mkDerivation {
      name = "codespell-1.14.0";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/b6/a0/954b77775d73c4943413d4aa486b8eb1a8864ea8e8941d55d4ce8e040b14/codespell-1.14.0.tar.gz";
        sha256 = "b1b60867773ffc5643a3724b62d12fe6797aa735831733f8a45f6d28db5ef34f";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/codespell-project/codespell/";
        license = "GPL v2";
        description = "Codespell";
      };
    };

    "colorama" = python.mkDerivation {
      name = "colorama-0.4.1";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/76/53/e785891dce0e2f2b9f4b4ff5bc6062a53332ed28833c7afede841f46a5db/colorama-0.4.1.tar.gz";
        sha256 = "05eed71e2e327246ad6b38c540c4a3117230b19679b875190486ddd2d721422d";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/tartley/colorama";
        license = licenses.bsdOriginal;
        description = "Cross-platform colored terminal text.";
      };
    };

    "coverage" = python.mkDerivation {
      name = "coverage-4.5.2";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/fb/af/ce7b0fe063ee0142786ee53ad6197979491ce0785567b6d8be751d2069e8/coverage-4.5.2.tar.gz";
        sha256 = "ab235d9fe64833f12d1334d29b558aacedfbca2356dfb9691f2d0d38a8a7bfb4";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://bitbucket.org/ned/coveragepy";
        license = licenses.asl20;
        description = "Code coverage measurement for Python";
      };
    };

    "coveralls" = python.mkDerivation {
      name = "coveralls-1.5.1";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/d2/4a/d0966ab522988667a9f23886dcec5cc029f1eb9848843466fbd2bb7a37fb/coveralls-1.5.1.tar.gz";
        sha256 = "ab638e88d38916a6cedbf80a9cd8992d5fa55c77ab755e262e00b36792b7cd6d";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [
        self."PyYAML"
        self."coverage"
        self."docopt"
        self."requests"
      ];
      meta = with pkgs.stdenv.lib; {
        homepage = "http://github.com/coveralls-clients/coveralls-python";
        license = licenses.mit;
        description = "Show coverage stats online via coveralls.io";
      };
    };

    "datadog" = python.mkDerivation {
      name = "datadog-0.26.0";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/17/dd/a7bbb33427f853f82b36356286fb922ef976bf18e78dbb76ac43b8c50e26/datadog-0.26.0.tar.gz";
        sha256 = "cbaa6b4b2b88fd552605e6730f60d5437017bb76d6b701432eaafbc983735b79";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [
        self."decorator"
        self."requests"
      ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://www.datadoghq.com";
        license = licenses.bsdOriginal;
        description = "The Datadog Python library";
      };
    };

    "decorator" = python.mkDerivation {
      name = "decorator-4.3.2";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/c4/26/b48aaa231644bc875bb348e162d156edb18b994da900a10f4493ea995a2f/decorator-4.3.2.tar.gz";
        sha256 = "33cd704aea07b4c28b3eb2c97d288a06918275dac0ecebdaf1bc8a48d98adb9e";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/micheles/decorator";
        license = "new BSD License";
        description = "Better living through Python with decorators";
      };
    };

    "docopt" = python.mkDerivation {
      name = "docopt-0.6.2";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/a2/55/8f8cab2afd404cf578136ef2cc5dfb50baa1761b68c9da1fb1e4eed343c9/docopt-0.6.2.tar.gz";
        sha256 = "49b3a825280bd66b3aa83585ef59c4a8c82f2c8a522dbe754a8bc8d08c85c491";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "http://docopt.org";
        license = licenses.mit;
        description = "Pythonic argument parser, that will make you smile";
      };
    };

    "docutils" = python.mkDerivation {
      name = "docutils-0.14";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/84/f4/5771e41fdf52aabebbadecc9381d11dea0fa34e4759b4071244fa094804c/docutils-0.14.tar.gz";
        sha256 = "51e64ef2ebfb29cae1faa133b3710143496eca21c530f3f71424d77687764274";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "http://docutils.sourceforge.net/";
        license = "public domain, Python, 2-Clause BSD, GPL 3 (see COPYING.txt)";
        description = "Docutils -- Python Documentation Utilities";
      };
    };

    "entrypoints" = python.mkDerivation {
      name = "entrypoints-0.3";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/b4/ef/063484f1f9ba3081e920ec9972c96664e2edb9fdc3d8669b0e3b8fc0ad7c/entrypoints-0.3.tar.gz";
        sha256 = "c70dd71abe5a8c85e55e12c19bd91ccfeec11a6e99044204511f9ed547d48451";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/takluyver/entrypoints";
        license = "UNKNOWN";
        description = "Discover and load entry points from installed packages.";
      };
    };

    "fancycompleter" = python.mkDerivation {
      name = "fancycompleter-0.8";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/fd/e3/da39a6cfaffe578a01221261ac1d5d99c48d44f6377ff0de3a12dd332cec/fancycompleter-0.8.tar.gz";
        sha256 = "d2522f1f3512371f295379c4c0d1962de06762eb586c199620a2a5d423539b12";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [
        self."setuptools-scm"
      ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "http://bitbucket.org/antocuni/fancycompleter";
        license = licenses.bsdOriginal;
        description = "colorful TAB completion for Python prompt";
      };
    };

    "flake8" = python.mkDerivation {
      name = "flake8-3.7.5";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/a2/6f/e81e1ec2396afdd9a8c1cddabd3ce47dc9a31160df782654c9d9979cd9e8/flake8-3.7.5.tar.gz";
        sha256 = "fd9ddf503110bf3d8b1d270e8c673aab29ccb3dd6abf29bae1f54e5116ab4a91";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [
        self."entrypoints"
        self."mccabe"
        self."pycodestyle"
        self."pyflakes"
      ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://gitlab.com/pycqa/flake8";
        license = licenses.mit;
        description = "the modular source code checker: pep8, pyflakes and co";
      };
    };

    "flake8-coding" = python.mkDerivation {
      name = "flake8-coding-1.3.1";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/f9/d7/889f7961ed549f15a280fa36edfc9b9016df38cd25cd0a8a7e4edc06efcf/flake8-coding-1.3.1.tar.gz";
        sha256 = "549c2b22c08711feda11795fb49f147a626305b602c547837bab405e7981f844";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [
        self."flake8"
      ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/tk0miya/flake8-coding";
        license = licenses.asl20;
        description = "Adds coding magic comment checks to flake8";
      };
    };

    "flake8-copyright" = python.mkDerivation {
      name = "flake8-copyright-0.2.2";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/66/35/3a5712611f8345329582817c71db68f6a1b6f4d500efeaeca1137b241417/flake8-copyright-0.2.2.tar.gz";
        sha256 = "5c3632dd8c586547b25fff4272282005fdbcba56eeb77b7487564aa636b6e533";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/savoirfairelinux/flake8-copyright";
        license = "UNKNOWN";
        description = "Adds copyright checks to flake8";
      };
    };

    "flake8-debugger" = python.mkDerivation {
      name = "flake8-debugger-3.1.0";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/39/4b/90548607282483dd15f9ce1f4434d735ae756e16e1faf60621b0f8877fcc/flake8-debugger-3.1.0.tar.gz";
        sha256 = "be4fb88de3ee8f6dd5053a2d347e2c0a2b54bab6733a2280bb20ebd3c4ca1d97";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [
        self."pytest-runner"
      ];
      propagatedBuildInputs = [
        self."flake8"
        self."pycodestyle"
      ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/jbkahn/flake8-debugger";
        license = licenses.mit;
        description = "ipdb/pdb statement checker plugin for flake8";
      };
    };

    "flake8-isort" = python.mkDerivation {
      name = "flake8-isort-2.6.0";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/85/fb/f2a33e47cf7520fd391e5f180cae5b8d2977ad7a5ddf897213137fe8a171/flake8-isort-2.6.0.tar.gz";
        sha256 = "3c107c405dd6e3dbdcccb2f84549d76d58a07120cd997a0560fab8b84c305f2a";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [
        self."flake8"
        self."isort"
        self."testfixtures"
      ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/gforcada/flake8-isort";
        license = "GPL version 2";
        description = "flake8 plugin that integrates isort .";
      };
    };

    "flake8-mypy" = python.mkDerivation {
      name = "flake8-mypy-17.8.0";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/97/9a/cddd1363d7314bb4eb452089c6fb3092ed9fda9f3350683d1978522a30ec/flake8-mypy-17.8.0.tar.gz";
        sha256 = "47120db63aff631ee1f84bac6fe8e64731dc66da3efc1c51f85e15ade4a3ba18";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [
        self."attrs"
        self."flake8"
        self."mypy"
      ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/ambv/flake8-mypy";
        license = licenses.mit;
        description = "A plugin for flake8 integrating mypy.";
      };
    };

    "flake8-quotes" = python.mkDerivation {
      name = "flake8-quotes-1.0.0";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/83/ff/0461010959158bb7d197691c696f1a85b20f2d3eea7aa23f73a8d07f30f3/flake8-quotes-1.0.0.tar.gz";
        sha256 = "fd9127ad8bbcf3b546fa7871a5266fd8623ce765ebe3d5aa5eabb80c01212b26";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [
        self."flake8"
      ];
      meta = with pkgs.stdenv.lib; {
        homepage = "http://github.com/zheller/flake8-quotes/";
        license = licenses.mit;
        description = "Flake8 lint for quotes.";
      };
    };

    "flit" = python.mkDerivation {
      name = "flit-1.3";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/1f/87/9ea76ab4cdf1fd36710d9688ec36a0053067c47e753b32272f952ff206c5/flit-1.3.tar.gz";
        sha256 = "6f6f0fb83c51ffa3a150fa41b5ac118df9ea4a87c2c06dff4ebf9adbe7b52b36";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [
        self."docutils"
        self."pytoml"
        self."requests"
      ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/takluyver/flit";
        license = "UNKNOWN";
        description = "A simple packaging tool for simple packages.";
      };
    };

    "idna" = python.mkDerivation {
      name = "idna-2.8";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/ad/13/eb56951b6f7950cadb579ca166e448ba77f9d24efc03edd7e55fa57d04b7/idna-2.8.tar.gz";
        sha256 = "c357b3f628cf53ae2c4c05627ecc484553142ca23264e593d327bcde5e9c3407";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/kjd/idna";
        license = licenses.bsdOriginal;
        description = "Internationalized Domain Names in Applications (IDNA)";
      };
    };

    "intreehooks" = python.mkDerivation {
      name = "intreehooks-1.0";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/f9/a5/5dacebf93232a847970921af2b020f9f2a8e0064e3a97727cd38efc77ba0/intreehooks-1.0.tar.gz";
        sha256 = "87e600d3b16b97ed219c078681260639e77ef5a17c0e0dbdd5a302f99b4e34e1";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [
        self."pytoml"
      ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/takluyver/intreehooks";
        license = "UNKNOWN";
        description = "Load a PEP 517 backend from inside the source tree";
      };
    };

    "isort" = python.mkDerivation {
      name = "isort-4.3.4";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/b1/de/a628d16fdba0d38cafb3d7e34d4830f2c9cb3881384ce5c08c44762e1846/isort-4.3.4.tar.gz";
        sha256 = "b9c40e9750f3d77e6e4d441d8b0266cf555e7cdabdcff33c4fd06366ca761ef8";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/timothycrosley/isort";
        license = licenses.mit;
        description = "A Python utility / library to sort Python imports.";
      };
    };

    "jmespath" = python.mkDerivation {
      name = "jmespath-0.9.3";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/e5/21/795b7549397735e911b032f255cff5fb0de58f96da794274660bca4f58ef/jmespath-0.9.3.tar.gz";
        sha256 = "6a81d4c9aa62caf061cb517b4d9ad1dd300374cd4706997aff9cd6aedd61fc64";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/jmespath/jmespath.py";
        license = licenses.mit;
        description = "JSON Matching Expressions";
      };
    };

    "mccabe" = python.mkDerivation {
      name = "mccabe-0.6.1";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/06/18/fa675aa501e11d6d6ca0ae73a101b2f3571a565e0f7d38e062eec18a91ee/mccabe-0.6.1.tar.gz";
        sha256 = "dd8d182285a0fe56bace7f45b5e7d1a6ebcbf524e8f3bd87eb0f125271b8831f";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [
        self."pytest-runner"
      ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/pycqa/mccabe";
        license = "Expat license";
        description = "McCabe checker, plugin for flake8";
      };
    };

    "mohawk" = python.mkDerivation {
      name = "mohawk-0.3.4";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/19/22/10f696548a8d41ad41b92ab6c848c60c669e18c8681c179265ce4d048b03/mohawk-0.3.4.tar.gz";
        sha256 = "e98b331d9fa9ece7b8be26094cbe2d57613ae882133cc755167268a984bc0ab3";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [
        self."six"
      ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/kumar303/mohawk";
        license = licenses.mpl20;
        description = "Library for Hawk HTTP authorization";
      };
    };

    "more-itertools" = python.mkDerivation {
      name = "more-itertools-6.0.0";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/dd/f4/cdfbb6f07f767e0cd8a11b16adfecc735b6eb87dbebda026ce8898e1cc22/more-itertools-6.0.0.tar.gz";
        sha256 = "590044e3942351a1bdb1de960b739ff4ce277960f2425ad4509446dbace8d9d1";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/erikrose/more-itertools";
        license = licenses.mit;
        description = "More routines for operating on iterables, beyond itertools";
      };
    };

    "mozdef-client" = python.mkDerivation {
      name = "mozdef-client-1.0.11";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/cd/9b/d783ba277e2120add2709e45db926f8e916c5933df2db9725b7787884ae5/mozdef_client-1.0.11.tar.gz";
        sha256 = "86b8c7065c21ce07d3095b5772f70fa152fe97258cde22311e5db4e34f5be26d";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [
        self."boto3"
        self."pytz"
        self."requests-futures"
      ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/gdestuynder/mozdef_client";
        license = "MPL";
        description = "A client library to send messages/events using MozDef";
      };
    };

    "mozilla-cli-common" = python.mkDerivation {
      name = "mozilla-cli-common-1.0.0";
      src = pkgs.lib.cleanSource ./../../../lib/cli_common;
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [
        self."Click"
        self."Logbook"
        self."aioamqp"
        self."mozdef-client"
        self."python-dateutil"
        self."python-hglib"
        self."raven"
        self."requests"
        self."structlog"
        self."taskcluster"
      ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/mozilla/release-services";
        license = licenses.mpl20;
        description = "Services behind https://mozilla-releng.net";
      };
    };

    "multidict" = python.mkDerivation {
      name = "multidict-4.5.2";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/7f/8f/b3c8c5b062309e854ce5b726fc101195fbaa881d306ffa5c2ba19efa3af2/multidict-4.5.2.tar.gz";
        sha256 = "024b8129695a952ebd93373e45b5d341dbb87c17ce49637b34000093f243dd4f";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/aio-libs/multidict";
        license = licenses.asl20;
        description = "multidict implementation";
      };
    };

    "mypy" = python.mkDerivation {
      name = "mypy-0.670";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/b3/69/68cca7d49c4a6856c2937ea794b9eb21102137503f924c6eca7c72664901/mypy-0.670.tar.gz";
        sha256 = "e80fd6af34614a0e898a57f14296d0dacb584648f0339c2e000ddbf0f4cc2f8d";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [
        self."mypy-extensions"
        self."typed-ast"
      ];
      meta = with pkgs.stdenv.lib; {
        homepage = "http://www.mypy-lang.org/";
        license = licenses.mit;
        description = "Optional static typing for Python";
      };
    };

    "mypy-extensions" = python.mkDerivation {
      name = "mypy-extensions-0.4.1";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/c2/92/3cc05d1206237d54db7b2565a58080a909445330b4f90a6436302a49f0f8/mypy_extensions-0.4.1.tar.gz";
        sha256 = "37e0e956f41369209a3d5f34580150bcacfabaa57b33a15c0b25f4b5725e0812";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "http://www.mypy-lang.org/";
        license = licenses.mit;
        description = "Experimental type system extensions for programs checked with the mypy typechecker.";
      };
    };

    "parsepatch" = python.mkDerivation {
      name = "parsepatch-0.1.3";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/d2/73/9eaedc53bdf9c5690d22812aaadce997634d74d2fbaf79f91b8f209be121/parsepatch-0.1.3.tar.gz";
        sha256 = "1f08654d3c737c7f43e5b5a03b078d0bb206684ba106df714db89f8c87fbd58a";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [
        self."requests"
      ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/mozilla/parsepatch";
        license = "MPL";
        description = "Library to parse patches in an efficient manner";
      };
    };

    "pathspec" = python.mkDerivation {
      name = "pathspec-0.5.9";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/84/2a/bfee636b1e2f7d6e30dd74f49201ccfa5c3cf322d44929ecc6c137c486c5/pathspec-0.5.9.tar.gz";
        sha256 = "54a5eab895d89f342b52ba2bffe70930ef9f8d96e398cccf530d21fa0516a873";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/cpburnz/python-path-specification";
        license = licenses.mpl20;
        description = "Utility library for gitignore style pattern matching of file paths.";
      };
    };

    "pdbpp" = python.mkDerivation {
      name = "pdbpp-0.9.6";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/6b/56/e797b18bfaa3632c5d4c928b72fe65b7be93967e7210b5b88addb7418bca/pdbpp-0.9.6.tar.gz";
        sha256 = "438bb2c885e40e9dcf649d9b598e4fe30fd1e3558c89a6ad3f447a9839a04e9f";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [
        self."setuptools-scm"
      ];
      propagatedBuildInputs = [
        self."Pygments"
        self."fancycompleter"
        self."wmctrl"
      ];
      meta = with pkgs.stdenv.lib; {
        homepage = "http://github.com/antocuni/pdb";
        license = licenses.bsdOriginal;
        description = "pdb++, a drop-in replacement for pdb";
      };
    };

    "pluggy" = python.mkDerivation {
      name = "pluggy-0.8.1";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/38/e1/83b10c17688af7b2998fa5342fec58ecbd2a5a7499f31e606ae6640b71ac/pluggy-0.8.1.tar.gz";
        sha256 = "8ddc32f03971bfdf900a81961a48ccf2fb677cf7715108f85295c67405798616";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/pytest-dev/pluggy";
        license = "MIT license";
        description = "plugin and hook calling mechanisms for python";
      };
    };

    "py" = python.mkDerivation {
      name = "py-1.7.0";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/c7/fa/eb6dd513d9eb13436e110aaeef9a1703437a8efa466ce6bb2ff1d9217ac7/py-1.7.0.tar.gz";
        sha256 = "bf92637198836372b520efcba9e020c330123be8ce527e535d185ed4b6f45694";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [
        self."setuptools-scm"
      ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "http://py.readthedocs.io/";
        license = "MIT license";
        description = "library with cross-python path, ini-parsing, io, code, log facilities";
      };
    };

    "pyasn1" = python.mkDerivation {
      name = "pyasn1-0.3.4";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/1a/37/7ac6910d872fdac778ad58c82018dce4af59279a79b17403bbabbe2a866e/pyasn1-0.3.4.tar.gz";
        sha256 = "3946ff0ab406652240697013a89d76e388344866033864ef2b097228d1f0101a";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/etingof/pyasn1";
        license = licenses.bsdOriginal;
        description = "ASN.1 types and codecs";
      };
    };

    "pycodestyle" = python.mkDerivation {
      name = "pycodestyle-2.5.0";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/1c/d1/41294da5915f4cae7f4b388cea6c2cd0d6cd53039788635f6875dfe8c72f/pycodestyle-2.5.0.tar.gz";
        sha256 = "e40a936c9a450ad81df37f549d676d127b1b66000a6c500caa2b085bc0ca976c";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://pycodestyle.readthedocs.io/";
        license = "Expat license";
        description = "Python style guide checker";
      };
    };

    "pyflakes" = python.mkDerivation {
      name = "pyflakes-2.1.0";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/48/6d/7bfd617b21292397e10e24af4cf42947a359b0c425b66f194cf5d14b1444/pyflakes-2.1.0.tar.gz";
        sha256 = "5e8c00e30c464c99e0b501dc160b13a14af7f27d4dffb529c556e30a159e231d";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/PyCQA/pyflakes";
        license = licenses.mit;
        description = "passive checker of Python programs";
      };
    };

    "pytest" = python.mkDerivation {
      name = "pytest-4.2.1";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/46/7a/567f671971c385103c3e3470e644946f36b3fade8fd0d2e55fa890062729/pytest-4.2.1.tar.gz";
        sha256 = "c2396a15726218a2dfef480861c4ba37bd3952ebaaa5b0fede3fc23fddcd7f8c";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [
        self."atomicwrites"
        self."attrs"
        self."more-itertools"
        self."pluggy"
        self."py"
        self."requests"
        self."six"
      ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://docs.pytest.org/en/latest/";
        license = "MIT license";
        description = "pytest: simple powerful testing with Python";
      };
    };

    "pytest-cov" = python.mkDerivation {
      name = "pytest-cov-2.6.1";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/54/16/4229c5514d12b25c3555ca775c7c3cade9a63da99b52fd5fc45962fa3d29/pytest-cov-2.6.1.tar.gz";
        sha256 = "0ab664b25c6aa9716cbf203b17ddb301932383046082c081b9848a0edf5add33";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [
        self."coverage"
        self."pytest"
      ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/pytest-dev/pytest-cov";
        license = licenses.mit;
        description = "Pytest plugin for measuring coverage.";
      };
    };

    "pytest-runner" = python.mkDerivation {
      name = "pytest-runner-4.4";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/15/0a/1e73c3a3d3f4f5faf5eacac4e55675c1627b15d84265b80b8fef3f8a3fb5/pytest-runner-4.4.tar.gz";
        sha256 = "00ad6cd754ce55b01b868a6d00b77161e4d2006b3918bde882376a0a884d0df4";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [
        self."setuptools-scm"
      ];
      propagatedBuildInputs = [
        self."pytest"
      ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/pytest-dev/pytest-runner";
        license = "UNKNOWN";
        description = "Invoke py.test as distutils command with dependency resolution";
      };
    };

    "python-dateutil" = python.mkDerivation {
      name = "python-dateutil-2.6.1";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/54/bb/f1db86504f7a49e1d9b9301531181b00a1c7325dc85a29160ee3eaa73a54/python-dateutil-2.6.1.tar.gz";
        sha256 = "891c38b2a02f5bb1be3e4793866c8df49c7d19baabf9c1bad62547e0b4866aca";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [
        self."six"
      ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://dateutil.readthedocs.io";
        license = "Simplified BSD";
        description = "Extensions to the standard Python datetime module";
      };
    };

    "python-hglib" = python.mkDerivation {
      name = "python-hglib-2.6.1";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/f9/39/4d8fa780f71347c3e25c6192f87e13a0265f44b9b8d0a36de550bf39e172/python-hglib-2.6.1.tar.gz";
        sha256 = "7c1fa0cb4d332dd6ec8409b04787ceba4623e97fb378656f7cab0b996c6ca3b2";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://www.mercurial-scm.org/wiki/PythonHglibs";
        license = licenses.mit;
        description = "Mercurial Python library";
      };
    };

    "pytoml" = python.mkDerivation {
      name = "pytoml-0.1.20";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/35/35/da1123673c54b6d701453fcd20f751d6a1fae43339b3993ae458875576e4/pytoml-0.1.20.tar.gz";
        sha256 = "ca2d0cb127c938b8b76a9a0d0f855cf930c1d50cc3a0af6d3595b566519a1013";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/avakar/pytoml";
        license = licenses.mit;
        description = "A parser for TOML-0.4.0";
      };
    };

    "pytz" = python.mkDerivation {
      name = "pytz-2018.9";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/af/be/6c59e30e208a5f28da85751b93ec7b97e4612268bb054d0dff396e758a90/pytz-2018.9.tar.gz";
        sha256 = "d5f05e487007e29e03409f9398d074e158d920d36eb82eaf66fb1136b0c5374c";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "http://pythonhosted.org/pytz";
        license = licenses.mit;
        description = "World timezone definitions, modern and historical";
      };
    };

    "raven" = python.mkDerivation {
      name = "raven-6.10.0";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/79/57/b74a86d74f96b224a477316d418389af9738ba7a63c829477e7a86dd6f47/raven-6.10.0.tar.gz";
        sha256 = "3fa6de6efa2493a7c827472e984ce9b020797d0da16f1db67197bcc23c8fae54";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/getsentry/raven-python";
        license = licenses.bsdOriginal;
        description = "Raven is a client for Sentry (https://getsentry.com)";
      };
    };

    "requests" = python.mkDerivation {
      name = "requests-2.21.0";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/52/2c/514e4ac25da2b08ca5a464c50463682126385c4272c18193876e91f4bc38/requests-2.21.0.tar.gz";
        sha256 = "502a824f31acdacb3a35b6690b5fbf0bc41d63a24a45c4004352b0242707598e";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [
        self."certifi"
        self."chardet"
        self."idna"
        self."urllib3"
      ];
      meta = with pkgs.stdenv.lib; {
        homepage = "http://python-requests.org";
        license = licenses.asl20;
        description = "Python HTTP for Humans.";
      };
    };

    "requests-futures" = python.mkDerivation {
      name = "requests-futures-0.9.9";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/e5/6b/c29ba0ce8d7d981c8099550148755846476c551f9e413801c0981f63ea91/requests-futures-0.9.9.tar.gz";
        sha256 = "200729e932ec1f6d6e58101a8d2b144d48c9695f0585bc1dcf37139190f699a1";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [
        self."requests"
      ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/ross/requests-futures";
        license = "Apache License v2";
        description = "Asynchronous Python HTTP for Humans.";
      };
    };

    "responses" = python.mkDerivation {
      name = "responses-0.10.5";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/c9/3b/bea0bfc243072a3d910befae4d1fb585276260abcac2a62109e01064c551/responses-0.10.5.tar.gz";
        sha256 = "c85882d2dc608ce6b5713a4e1534120f4a0dc6ec79d1366570d2b0c909a50c87";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [
        self."requests"
        self."six"
      ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/getsentry/responses";
        license = licenses.asl20;
        description = "A utility library for mocking out the `requests` Python library.";
      };
    };

    "s3transfer" = python.mkDerivation {
      name = "s3transfer-0.2.0";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/43/22/37b9aaf3969628a25b3b921612139ebc5b8dc26cabb9873c356e1ad2ce2e/s3transfer-0.2.0.tar.gz";
        sha256 = "f23d5cb7d862b104401d9021fc82e5fa0e0cf57b7660a1331425aab0c691d021";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [
        self."botocore"
      ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/boto/s3transfer";
        license = licenses.asl20;
        description = "An Amazon S3 Transfer Manager";
      };
    };

    "setuptools-scm" = python.mkDerivation {
      name = "setuptools-scm-3.2.0";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/54/85/514ba3ca2a022bddd68819f187ae826986051d130ec5b972076e4f58a9f3/setuptools_scm-3.2.0.tar.gz";
        sha256 = "52ab47715fa0fc7d8e6cd15168d1a69ba995feb1505131c3e814eb7087b57358";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/pypa/setuptools_scm/";
        license = licenses.mit;
        description = "the blessed package to manage your versions by scm tags";
      };
    };

    "six" = python.mkDerivation {
      name = "six-1.10.0";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/b3/b2/238e2590826bfdd113244a40d9d3eb26918bd798fc187e2360a8367068db/six-1.10.0.tar.gz";
        sha256 = "105f8d68616f8248e24bf0e9372ef04d3cc10104f1980f54d57b2ce73a5ad56a";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "http://pypi.python.org/pypi/six/";
        license = licenses.mit;
        description = "Python 2 and 3 compatibility utilities";
      };
    };

    "slugid" = python.mkDerivation {
      name = "slugid-1.0.7";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/dd/96/b05c6d357f8d6932bea2b360537360517d1154b82cc71b8eccb70b28bdde/slugid-1.0.7.tar.gz";
        sha256 = "6dab3c7eef0bb423fb54cb7752e0f466ddd0ee495b78b763be60e8a27f69e779";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "http://taskcluster.github.io/slugid.py";
        license = licenses.mpl20;
        description = "Base64 encoded uuid v4 slugs";
      };
    };

    "structlog" = python.mkDerivation {
      name = "structlog-19.1.0";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/e7/e8/988ab8398bd0a445ba2093702caaebd394a303e534f6dddea733a2aada77/structlog-19.1.0.tar.gz";
        sha256 = "5feae03167620824d3ae3e8915ea8589fc28d1ad6f3edf3cc90ed7c7cb33fab5";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [
        self."six"
      ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://www.structlog.org/";
        license = licenses.mit;
        description = "Structured Logging for Python";
      };
    };

    "taskcluster" = python.mkDerivation {
      name = "taskcluster-6.0.0";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/06/6a/66bf42549bb69618159b0515c3001b9b8c21bbb5b28f16fcb14cfeef3318/taskcluster-6.0.0.tar.gz";
        sha256 = "48ecd4898c7928deddfb34cb1cfe2b2505c68416e6c503f8a7f3dd0572425e96";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [
        self."aiohttp"
        self."async-timeout"
        self."mohawk"
        self."requests"
        self."six"
        self."slugid"
        self."taskcluster-urls"
      ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/taskcluster/taskcluster-client.py";
        license = "UNKNOWN";
        description = "Python client for Taskcluster";
      };
    };

    "taskcluster-urls" = python.mkDerivation {
      name = "taskcluster-urls-11.0.0";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/69/c1/1f0efd104c7bd6dbb42a7d0c7f1f5f4be05c108e873add8f466e6de9f387/taskcluster-urls-11.0.0.tar.gz";
        sha256 = "18dcaa9c2412d34ff6c78faca33f0dd8f2384e3f00a98d5832c62d6d664741f0";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/taskcluster/taskcluster-lib-urls";
        license = licenses.mpl20;
        description = "Standardized url generator for taskcluster resources.";
      };
    };

    "testfixtures" = python.mkDerivation {
      name = "testfixtures-6.5.0";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/d3/06/52f46d4e05c5d923e384976d057ca14a0d90c561cd150bebe7e04a9ffe15/testfixtures-6.5.0.tar.gz";
        sha256 = "cbd0f095d178de578709bcf4cc6eea896964635d2b41386d1cc7583674809b0e";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/Simplistix/testfixtures";
        license = licenses.mit;
        description = "A collection of helpers and mock objects for unit tests and doc tests.";
      };
    };

    "texttable" = python.mkDerivation {
      name = "texttable-1.6.1";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/04/c6/7d2514d76fefba65bfe2fa4e1082c3adea9edef5a149a3027b8f2d5ee0eb/texttable-1.6.1.tar.gz";
        sha256 = "2b60a5304ccfbeac80ffae7350d7c2f5d7a24e9aab5036d0f82489746419d9b2";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/foutaise/texttable/";
        license = licenses.mit;
        description = "module for creating simple ASCII tables";
      };
    };

    "tqdm" = python.mkDerivation {
      name = "tqdm-4.31.1";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/80/9b/f3036a9a11c250eb51d38acf94d1d7c33a0d4da8a8931bfdf15e12d505b1/tqdm-4.31.1.tar.gz";
        sha256 = "e22977e3ebe961f72362f6ddfb9197cc531c9737aaf5f607ef09740c849ecd05";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/tqdm/tqdm";
        license = "MPLv2.0, MIT Licences";
        description = "Fast, Extensible Progress Meter";
      };
    };

    "typed-ast" = python.mkDerivation {
      name = "typed-ast-1.3.1";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/fc/c6/61d6410fc70fda073bd1810f9b7f7022f00146b108f278a0c00041bfe5b0/typed-ast-1.3.1.tar.gz";
        sha256 = "606d8afa07eef77280c2bf84335e24390055b478392e1975f96286d99d0cb424";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/python/typed_ast";
        license = licenses.asl20;
        description = "a fork of Python 2 and 3 ast modules with type comment support";
      };
    };

    "urllib3" = python.mkDerivation {
      name = "urllib3-1.24.1";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/b1/53/37d82ab391393565f2f831b8eedbffd57db5a718216f82f1a8b4d381a1c1/urllib3-1.24.1.tar.gz";
        sha256 = "de9529817c93f27c8ccbfead6985011db27bd0ddfcdb2d86f3f663385c6a9c22";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [
        self."certifi"
        self."idna"
      ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://urllib3.readthedocs.io/";
        license = licenses.mit;
        description = "HTTP library with thread-safe connection pooling, file post, and more.";
      };
    };

    "wmctrl" = python.mkDerivation {
      name = "wmctrl-0.3";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/01/c6/001aefbde5782d6f359af0a8782990c3f4e751e29518fbd59dc8dfc58b18/wmctrl-0.3.tar.gz";
        sha256 = "d806f65ac1554366b6e31d29d7be2e8893996c0acbb2824bbf2b1f49cf628a13";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "http://bitbucket.org/antocuni/wmctrl";
        license = licenses.bsdOriginal;
        description = "A tool to programmatically control windows inside X";
      };
    };

    "yamllint" = python.mkDerivation {
      name = "yamllint-1.15.0";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/47/79/5abf604a4ad4b74c12a4f47d1ef166a6702a4d86cb6dccc07d5996969dfb/yamllint-1.15.0.tar.gz";
        sha256 = "8f25759997acb42e52b96bf3af0b4b942e6516b51198bebd3402640102006af7";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [
        self."PyYAML"
        self."pathspec"
      ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/adrienverge/yamllint";
        license = "GPLv3";
        description = "A linter for YAML files.";
      };
    };

    "yarl" = python.mkDerivation {
      name = "yarl-1.3.0";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/fb/84/6d82f6be218c50b547aa29d0315e430cf8a23c52064c92d0a8377d7b7357/yarl-1.3.0.tar.gz";
        sha256 = "024ecdc12bc02b321bc66b41327f930d1c2c543fa9a561b39861da9388ba7aa9";
      };
      doCheck = commonDoCheck;
      checkPhase = "";
      installCheckPhase = "";
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [
        self."idna"
        self."multidict"
      ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/aio-libs/yarl/";
        license = licenses.asl20;
        description = "Yet another URL library";
      };
    };
  };
  localOverridesFile = ./requirements_override.nix;
  localOverrides = import localOverridesFile { inherit pkgs python; };
  commonOverrides = [
        (import ../../../nix/requirements_override.nix { inherit pkgs python ; })
  ];
  paramOverrides = [
    (overrides { inherit pkgs python; })
  ];
  allOverrides =
    (if (builtins.pathExists localOverridesFile)
     then [localOverrides] else [] ) ++ commonOverrides ++ paramOverrides;

in python.withPackages
   (fix' (pkgs.lib.fold
            extends
            generated
            allOverrides
         )
   )