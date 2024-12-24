# MaaFrameworkUpdater

适用于MaaFramework通用模板项目的自动更新工具。

## 命令行参数

### 参数说明

- `--base-dir your_project_dir`：

  将基础目录设置为 your_project_dir，该目录为项目文件的存放位置。
  如果未指定此参数，默认使用当前目录 (.)。

- `--diff-dir patch_save_dir`：

  将差异文件保存到 patch_save_dir 目录中。
  如果未指定此参数，默认使用 patch 目录。

- `--prerelease`：

  如果包含此选项，将包括预发布版本。
  如果不包含此选项，则只包含正式发布版本。

- `--token your_github_token`：

这是一个必须参数，指定你的 GitHub 访问令牌，用于访问 GitHub API。
请确保你的 GitHub 令牌具有访问所需资源的权限。

### 示例

```bash
python updater.py --base-dir M9A-v2.6.7 --diff-dir patch --prerelease --token xxxxxx
```

### 获取 token

本项目使用 GitHub API 进行项目最新版本的获取及更新，为保证最佳体验，可能需要您填写参照以下链接获取 token：  
[管理个人访问令牌](https://docs.github.com/zh/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)

fine-grained personal access token 最佳，且生成时不要超过366天有效期。
