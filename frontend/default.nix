{ releng_pkgs
}:

releng_pkgs.lib.mkYarnFrontend {
  name = "mozilla-staticanalysis-frontend";
  src = ./.;
  src_path = "src/staticanalysis/frontend";
  csp = "default-src 'none'; img-src 'self' data:; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self';";
  extraBuildInputs = with releng_pkgs.pkgs; [
    libpng
    libpng.dev
    pkgconfig
  ];
}
