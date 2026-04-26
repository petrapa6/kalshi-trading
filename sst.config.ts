/// <reference path="./.sst/platform/config.d.ts" />

export default $config({
  app(input) {
    return {
      name: "predictions",
      removal: input?.stage === "production" ? "retain" : "remove",
      home: "aws",
      providers: {
        aws: {
          region: "us-east-2",
        },
        cloudflare: true,
      },
    };
  },
  async run() {
    const dashboardPassword = new sst.Secret("DashboardPassword");
    const kalshiApiKey = new sst.Secret("KalshiApiKey");
    const kalshiPrivateKey = new sst.Secret("KalshiPrivateKey");
    const apiToken = new sst.Secret("ApiToken");
    const footballDataApiKey = new sst.Secret("FootballDataApiKey");

    const backupBucket = new sst.aws.Bucket("DbBackups");

    // const vpc = new sst.aws.Vpc("Vpc", { nat: "ec2" });
    const vpc = new sst.aws.Vpc("Vpc", {
      nat: {
        type: "ec2",
        ec2: {
          instance: "t3.micro",
          // ami: "ami-0b9231f82f8021184"
          ami: "ami-0260a965768f1f48b"
        },
      },
    });

    const cluster = new sst.aws.Cluster("Cluster", { vpc });



    // API + Scanner on single ECS service (saves ~$9/mo)
    const api = cluster.addService("Api", {
      image: {
        context: ".",
        dockerfile: "Dockerfile",
        buildArgs: { CACHE_BUST: Date.now().toString() },
      },
      cpu: "0.25 vCPU",
      memory: "0.5 GB",
      link: [backupBucket],
      environment: {
        DATABASE_URL: $dev
          ? "sqlite:///predictions.db"
          : "sqlite:////tmp/predictions.db",
          KALSHI_API_KEY: kalshiApiKey.value,
          KALSHI_PRIVATE_KEY: kalshiPrivateKey.value,
          MIN_YES_PRICE: "92",
          BET_PERCENT: "5.0",
          POLL_INTERVAL_SECONDS: "10",
          DRY_RUN: $dev ? "true" : "false",
          API_TOKEN: apiToken.value,
          DB_BACKUP_BUCKET: backupBucket.name,
          FOOTBALL_DATA_API_KEY: footballDataApiKey.value,
          SOCCER_CACHE_DB_PATH: "/tmp/soccer-cache.db",
          CORS_ORIGINS: "https://your-domain.example",
      },

      public: {
        ports: [{ listen: "443/https", forward: "8000/http" }],
        domain: {
          name: "api.your-domain.example",
          dns: sst.cloudflare.dns(),
        },
      },
      dev: {
        command: "pnpm dev:api",
        url: "http://localhost:8000",
      },
    });

    // Next.js dashboard via OpenNext (Lambda/CloudFront)
    const dashboard = new sst.aws.Nextjs("Dashboard", {
      path: "dashboard",
      domain: {
        name: "your-domain.example",
        dns: sst.cloudflare.dns(),
      },
      environment: {
        NEXT_PUBLIC_API_URL: $interpolate`${api.url}`.apply((v) => v.replace(/\/+$/, "")),
          DASHBOARD_PASSWORD: dashboardPassword.value,
          API_TOKEN: apiToken.value,
      },
      // Update this section:
      imageOptimization: {
        staticEtag: true,
      },
      transform: {
        // SST expects the URL toggle here for the underlying Lambda
        imageOptimizer: (args) => {
          args.url = true;
        },
      },
    });

    return {
      api: api.url,
      dashboard: dashboard.url,
    };
  },
});
