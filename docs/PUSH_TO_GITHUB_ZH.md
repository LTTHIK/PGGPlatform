# 推送到 GitHub 说明

仓库已在本地初始化并完成首次提交，远程：

```text
https://github.com/LTTHIK/PGGPlatform.git
```

## 方式一：Personal Access Token（推荐）

1. GitHub → Settings → Developer settings → Personal access tokens → 生成 **repo** 权限 token  
2. 在本机执行（将 `YOUR_TOKEN` 替换为 token）：

```bash
cd /mnt/dockerContainerSave/memory/ltt/workspace
git push https://LTTHIK:YOUR_TOKEN@github.com/LTTHIK/PGGPlatform.git main
```

或配置 credential helper 后：

```bash
git push -u origin main
# Username: LTTHIK
# Password: <粘贴 token，不是 GitHub 登录密码>
```

## 方式二：SSH

```bash
# 生成密钥并添加到 GitHub SSH keys 后
git remote set-url origin git@github.com:LTTHIK/PGGPlatform.git
git push -u origin main
```

## 已排除（勿手动 add）

- `base_Platform/.env`（含 MinIO/JWT 密钥）
- `**/basePlatformltt_env/`、`**/graphragltt_env/`
- `paraformer_model/`、`recordings/`、`graphrag_runs/`
- `node_modules/`

首次部署请复制 `base_Platform/.env.example` → `.env`。

## 嵌套 Git 处理

为合并为单一仓库，已重命名：

- `graphrag/.git` → `graphrag/.git.vendor-backup-microsoft-graphrag`
- `hermes-agent/.git` → `hermes-agent/.git.vendor-backup-hermes`

若需恢复 upstream 跟踪，可改回目录名。
