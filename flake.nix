{
  description = "Fluid Python ML Environment for NixOS";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs {
        inherit system;
        config.allowUnfree = true; # Required if you end up using CUDA or other proprietary tools
      };
    in
    {
      devShells.${system}.default = pkgs.mkShell {
        # 1. Packages available in your shell
        packages = with pkgs; [
          python311
          uv           # Ultra-fast Rust-based Python package manager
          git
        ];

        # 2. The Magic Sauce: LD_LIBRARY_PATH
        # Pre-compiled Python wheels (like PyTorch) expect standard Linux C libraries.
        # This tells the shell exactly where to find them in the Nix store.
        LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath (with pkgs; [
          stdenv.cc.cc.lib # Crucial for libstdc++.so.6
          zlib             # Needed for compression
          glib             # Common C library
          libGL            # Needed for OpenCV (cv2)
          xorg.libX11      # Needed for GUI/Plotting stuff

          # IF YOU HAVE AN NVIDIA GPU, uncomment these three lines:
          # linuxPackages.nvidia_x11
          # cudaPackages.cudatoolkit
          # cudaPackages.cudnn
        ]);

        # 3. Automation on entering the shell
        shellHook = ''
          # Set up the virtual environment automatically using uv
          if [ ! -d .venv ]; then
            echo "Creating virtual environment using uv..."
            uv venv
          fi

          # Activate the virtual environment
          source .venv/bin/activate

          echo "🚀 Python environment ready!"
          echo "You can now drop in packages fluidly (e.g., 'uv pip install torch numpy pandas')."
        '';
      };
    };
}
