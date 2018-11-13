{ releng_pkgs
}:
let
  inherit (releng_pkgs.pkgs.lib) fileContents;

in releng_pkgs.lib.mkYarnFrontend {
  project_name = "staticanalysis/frontend";
  version = fileContents ./VERSION;
  src = ./.;
  csp = "default-src 'none'; img-src 'self' data:; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self';";
  extraBuildInputs = with releng_pkgs.pkgs; [
    libpng
    libpng.dev
    pkgconfig
  ];
}
