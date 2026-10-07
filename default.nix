{ pkgs ? import <nixpkgs> { }
, lib ? pkgs.lib
, python3Packages ? pkgs.python3Packages
}:

let
  pypkgs = python3Packages;

  vosk = pypkgs.buildPythonPackage rec {
    pname = "vosk";
    version = "0.3.45";
    format = "wheel";
    src = pkgs.fetchurl {
      url = "https://files.pythonhosted.org/packages/fc/ca/83398cfcd557360a3d7b2d732aee1c5f6999f68618d1645f38d53e14c9ff/vosk-0.3.45-py3-none-manylinux_2_12_x86_64.manylinux2010_x86_64.whl";
      sha256 = "25e025093c4399d7278f543568ed8cc5460ac3a4bf48c23673ace1e25d26619f";
    };
    nativeBuildInputs = [ pkgs.autoPatchelfHook ];
    buildInputs = [ pkgs.stdenv.cc.cc.lib ];
    propagatedBuildInputs = with pypkgs; [
      cffi
      requests
      srt
      tqdm
      websockets
    ];
    doCheck = false;
  };

  runtimeDeps = with pkgs; [
    mpv
    brightnessctl
    upower
    wireplumber
    pulseaudio
    usbutils
    android-tools
    espeak-ng
    whisper-cpp
    playerctl
  ];

in
pypkgs.buildPythonApplication rec {
  pname = "stewart";
  version = "1.9.3.1";
  pyproject = true;

  src = lib.cleanSourceWith {
    src = ./.;
    filter = path: type:
      let base = baseNameOf path; in
      !(base == ".git"
        || base == ".venv"
        || base == ".backup"
        || base == ".idea"
        || base == "__pycache__"
        || base == "docs"
        || base == "models"
        || base == "dataset"
        || base == "result");
  };

  nativeBuildInputs = [
    pypkgs.setuptools
    pypkgs.wheel
    pypkgs.pythonRelaxDepsHook
    pkgs.makeWrapper
  ];

  pythonRemoveDeps = [
    "python-mpv"
  ];

  propagatedBuildInputs = with pypkgs; [
    pyyaml
    num2words
    yt-dlp
    python-dotenv
    pynput
    numpy
    pydub
    mpv
    requests
    lxml
    beautifulsoup4
    plyer
    ytmusicapi
    icalendar
    pyaudio
    soundfile
    kokoro
    torch
    scipy
    vosk
    faster-whisper
    pydantic
    json-repair
  ];

  makeWrapperArgs = [
    "--prefix PATH : ${lib.makeBinPath runtimeDeps}"
    "--prefix LD_LIBRARY_PATH : ${lib.makeLibraryPath [ pkgs.mpv pkgs.portaudio pkgs.stdenv.cc.cc.lib ]}"
  ];

  doCheck = false;

  meta = with lib; {
    description = "Voice assistant for Linux";
    homepage = "https://github.com/ilyamiro/stewart";
    license = licenses.gpl3Only;
    platforms = platforms.linux;
    mainProgram = "stewart";
  };
}
