{
  description = "Trade Tracker — track trades on the Optimism network";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python3;

        trade-tracker = python.pkgs.buildPythonPackage rec {
          pname = "trade-tracker";
          version = "0.1.0";
          pyproject = true;
          src = ./.;

          nativeBuildInputs = with python.pkgs; [ setuptools ];

          propagatedBuildInputs = with python.pkgs; [
            web3
            click
            requests
            clickhouse-driver
            python-dotenv
          ];

          pythonImportsCheck = [
            "trade_tracker"
            "trade_tracker.cli"
            "trade_tracker.models"
            "trade_tracker.blockchain"
          ];
        };
      in
      {
        packages.default = trade-tracker;

        apps.default = {
          type = "app";
          program = "${trade-tracker}/bin/trade-tracker";
        };

        devShells.default = pkgs.mkShell {
          inputsFrom = [ trade-tracker ];

          packages = with pkgs; [
            trade-tracker
            python.pkgs.pytest
            python.pkgs.pytest-cov
            ruff
          ];

          shellHook = ''
            echo "trade-tracker dev shell ready"
          '';
        };
      }
    ) // {
      nixosModules.default = { pkgs, ... }: {
        nixpkgs.overlays = [
          (final: prev: {
            trade-tracker = self.packages.${final.system}.default;
          })
        ];
        imports = [ ./nixos-module.nix ];
      };
    };
}
