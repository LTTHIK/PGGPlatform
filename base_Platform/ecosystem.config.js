module.exports = {
  apps: [
    {
      name: "fastapi-backend",
      script: ".venv/bin/python",
      args: "-m uvicorn backend.app:app --host 0.0.0.0 --port 18000",
      interpreter: "none",
      cwd: "/mnt/dockerContainerSave/base_platform/minimal_craft_deploy",
      instances: 1,
      exec_mode: "fork",
      autorestart: true,
      watch: false,
      max_memory_restart: "2G",
      env: {
        NODE_ENV: "production"
      },
      error_file: "./logs/backend-error.log",
      out_file: "./logs/backend-out.log",
      log_file: "./logs/backend-combined.log",
      time: true
    },
    {
      name: "vite-frontend",
      script: "npm",
      args: "run dev -- --host 0.0.0.0 --port 5173",
      cwd: "/mnt/dockerContainerSave/base_platform/minimal_craft_deploy/frontend",
      instances: 1,
      exec_mode: "fork",
      autorestart: true,
      watch: false,
      env: {
        NODE_ENV: "development"
      },
      error_file: "./logs/frontend-error.log",
      out_file: "./logs/frontend-out.log",
      time: true
    }
  ]
};
