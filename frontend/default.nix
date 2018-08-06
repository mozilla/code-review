{ releng_pkgs
}:

releng_pkgs.lib.mkYarnFrontend {
  src = ./.;
  src_path = ./.;
}
