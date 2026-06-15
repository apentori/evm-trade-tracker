{ config, lib, pkgs, ... }:

let
  cfg = config.services.trade-tracker;
  yamlFormat = pkgs.formats.yaml { };

  defaultTopicTypes = {
    "0x40e9cecb9f5f1f1c5b9c97dec2917b7ee92e57ba5563708daca94dd84ad7112f" = "SWAP";
    "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef" = "TRANSFER";
    "0x7fcf532c15f0a6db0bd6d0e038bea71d30d808c7d98cb3bf7268a95bf5081b65" = "WITHDRAWAL";
  };

  defaultPairs = [
    {
      name = "ETH/USDC";
      base_token = "0x4200000000000000000000000000000000000006";
      quote_token = "0x0b2c639c533813f4aa9d7837caf62653d097ff85";
      base_decimals = 18;
      quote_decimals = 6;
    }
    {
      name = "ETH/DAI";
      base_token = "0x4200000000000000000000000000000000000006";
      quote_token = "0xda10009cbd5d07dd0cecc66161fc93d7c9000da1";
      base_decimals = 18;
      quote_decimals = 6;
    }
  ];

  configYaml = yamlFormat.generate "trade-tracker.yaml" {
    alchemy = {
      url = cfg.alchemyUrl;
    };
    clickhouse = {
      host = cfg.clickhouse.host;
      port = cfg.clickhouse.port;
      user = cfg.clickhouse.user;
      database = cfg.clickhouse.database;
      table = cfg.clickhouse.table;
    };
    pairs = cfg.pairs;
    events.topic_types = cfg.eventTopicTypes;
    null_address = cfg.nullAddress;
    log_level = cfg.logLevel;
  };
in
{
  options.services.trade-tracker = {
    enable = lib.mkEnableOption "Trade Tracker service";

    environmentFile = lib.mkOption {
      type = lib.types.str;
      default = "/etc/trade-tracker/secrets.env";
      description = ''
        Path to environment file containing secrets.
        Must define: ALCHEMY_API_KEY, WALLET_ADDRESS, and optionally CLICKHOUSE_PASSWORD.
        Example content:
          ALCHEMY_API_KEY=your-key
          WALLET_ADDRESS=0xdead...
          CLICKHOUSE_PASSWORD=s3cret
        Create with: sudo chmod 600 /etc/trade-tracker/secrets.env
      '';
    };

    alchemyUrl = lib.mkOption {
      type = lib.types.str;
      default = "https://opt-mainnet.g.alchemy.com/v2";
      description = "Alchemy RPC URL";
    };

    clickhouse = {
      host = lib.mkOption {
        type = lib.types.str;
        default = "localhost";
      };
      port = lib.mkOption {
        type = lib.types.port;
        default = 9000;
      };
      user = lib.mkOption {
        type = lib.types.str;
        default = "default";
      };
      database = lib.mkOption {
        type = lib.types.str;
        default = "default";
      };
      table = lib.mkOption {
        type = lib.types.str;
        default = "trades";
      };
    };

    pairs = lib.mkOption {
      type = lib.types.listOf (lib.types.submodule {
        options = {
          name = lib.mkOption {
            type = lib.types.str;
            description = "Display name for this pair (e.g. ETH/USDC)";
          };
          base_token = lib.mkOption {
            type = lib.types.str;
            description = "Address of the base token (what's being bought/sold)";
          };
          quote_token = lib.mkOption {
            type = lib.types.str;
            description = "Address of the quote token (payment asset)";
          };
          base_decimals = lib.mkOption {
            type = lib.types.int;
            default = 18;
          };
          quote_decimals = lib.mkOption {
            type = lib.types.int;
            default = 6;
          };
        };
      });
      default = defaultPairs;
      description = "List of trading pairs to detect";
    };

    eventTopicTypes = lib.mkOption {
      type = lib.types.attrsOf lib.types.str;
      default = defaultTopicTypes;
      description = "Map of event signature hashes to human-readable names";
    };

    nullAddress = lib.mkOption {
      type = lib.types.str;
      default = "0x0000000000000000000000000000000000000000";
    };

    logLevel = lib.mkOption {
      type = lib.types.str;
      default = "INFO";
    };

    follow = lib.mkOption {
      type = lib.types.bool;
      default = true;
      description = "Enable follow mode (auto-detect from last stored block)";
    };

    timerInterval = lib.mkOption {
      type = lib.types.str;
      default = "hourly";
      example = "*-*-* *:00:00";
      description = "systemd OnCalendar interval for the timer";
    };
  };

  config = lib.mkIf cfg.enable {
    environment.etc."trade-tracker/config.yaml".source = configYaml;

    systemd.services.trade-tracker = {
      description = "Trade Tracker — scan wallet for trades";
      after = [ "network.target" ];
      wants = [ "network.target" ];

      serviceConfig = {
        Type = "oneshot";
        ExecStart =
          "${pkgs.trade-tracker}/bin/trade-tracker"
          + " --config /etc/trade-tracker/config.yaml"
          + lib.optionalString cfg.follow " --follow";
        EnvironmentFile = cfg.environmentFile;
        UMask = "0077";
      };
    };

    systemd.timers.trade-tracker = {
      description = "Trade Tracker — periodic scan timer";
      wantedBy = [ "timers.target" ];

      timerConfig = {
        OnCalendar = cfg.timerInterval;
        Persistent = true;
      };
    };
  };
}
