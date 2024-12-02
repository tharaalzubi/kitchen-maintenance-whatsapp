{pkgs}: {
  deps = [
    pkgs.tree
    pkgs.mailutils
    pkgs.nano
    pkgs.postgresql
    pkgs.lsof
    pkgs.libxcrypt
    pkgs.python312Packages.pyngrok
  ];
}
