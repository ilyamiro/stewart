{ pkgs ? import <nixpkgs> {
    config = {
      allowUnfree = true;
      cudaSupport = true;
    };
  }
}:

let
  lib = pkgs.lib;
  python = pkgs.python311;
  libs = with pkgs; [
    stdenv.cc.cc.lib
    zlib
    glib
    libGL
    openssl
    mpv
    portaudio
    libffi
    readline
    bzip2
    sqlite
  ];
in
pkgs.mkShell {
  name = "stewart-shell";

  packages = [
    python
    pkgs.uv
    pkgs.git
    pkgs.which
    pkgs.pkg-config
    pkgs.mpv
    pkgs.portaudio
    pkgs.playerctl
    pkgs.brightnessctl
  ];

  shellHook = ''
    export LD_LIBRARY_PATH="/run/opengl-driver/lib:/run/opengl-driver-32/lib:${lib.makeLibraryPath libs}:''${LD_LIBRARY_PATH:-}"
    export CUDA_HOME="/run/opengl-driver"
    export UV_PYTHON="${python}/bin/python"

    echo "=== Stewart Dev Shell Ready ==="
    echo "Python: $(${python}/bin/python --version)"
    echo "uv: $(uv --version)"
  '';
}
