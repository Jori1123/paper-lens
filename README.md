# Paper Lens · 论文镜像

近十年中英双语论文检索网站。支持全文关键词检索、年份与领域筛选、开放获取过滤，以及按时间、引用数和知名度排序；论文阅读器可切换原版、汉译和双语对照。

## 启动网站

```bash
cd ~/paper_lens
python3 server.py
```

浏览器会打开 <http://127.0.0.1:8788>。使用 `python3 server.py --no-browser --port 9000` 可修改启动行为。

## 公网网站

网站通过 GitHub Pages 自动发布。每次推送到 `main` 分支都会重新部署，GitHub Actions 每天北京时间 06:20 从 OpenAlex 增量更新论文。

部署工作流位于 `.github/workflows/pages.yml`。若需自动汉译，在仓库设置中创建 Actions Secret `OPENAI_API_KEY`；还可创建 `OPENAI_BASE_URL`、`OPENAI_MODEL` 和 `OPENALEX_EMAIL` Repository Variables。

## 手动更新论文

数据来自 [OpenAlex API](https://docs.openalex.org/)，脚本遵循 API 而非抓取网页，不需要第三方 Python 包：

```bash
cd ~/paper_lens
python3 scripts/update_papers.py
```

默认按五个主要研究方向分别获取 40 篇高引用论文，与现有数据按 DOI 去重，并原子写入 `data/papers.json`。可调整关键词与数量：

```bash
python3 scripts/update_papers.py \
  --queries "embodied intelligence" "robot learning" \
  --per-query 100
```

建议通过 `OPENALEX_EMAIL=you@example.com` 提供联系邮箱，以使用 OpenAlex polite pool。

## 自动更新

在使用 systemd 的 Linux 桌面或服务器上执行：

```bash
cd ~/paper_lens
bash scripts/install_automation.sh
```

安装器会创建用户级定时器，每 6 小时运行一次增量同步，不需要 root 权限。常用管理命令：

```bash
systemctl --user status paper-lens-update.timer
systemctl --user start paper-lens-update.service
systemctl --user disable --now paper-lens-update.timer
```

日志保存在 `data/logs/update.log`。定时器带持久化与随机延迟，`auto_update.sh` 使用文件锁避免任务重叠。

## 自动汉译（可选）

更新脚本保留已有汉译；新论文默认进入“待翻译”状态。可接入本地 LibreTranslate：

```bash
cat > .env.update <<'EOF'
PAPER_LENS_TRANSLATE=libretranslate
LIBRETRANSLATE_URL=http://127.0.0.1:5000
PAPER_LENS_TRANSLATE_LIMIT=20
OPENALEX_EMAIL=you@example.com
EOF
```

也可使用 OpenAI 兼容接口：

```bash
cat > .env.update <<'EOF'
PAPER_LENS_TRANSLATE=openai
OPENAI_API_KEY=your-key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
EOF
```

`.env.update` 与翻译缓存不会进入版本库。请确认所用翻译服务的费用、隐私和内容条款。

## 知名度计算

知名度不是学术质量判断。当前分数范围为 0—100，由引用数的对数归一化（82%）和近十年新近程度（18%）合成。界面同时显示原始引用数，便于用户自行判断。

## 测试

```bash
python3 -m unittest discover -s tests -v
python3 -m json.tool data/papers.json >/dev/null
```

## 文件结构

```text
index.html                  页面结构
styles.css                 响应式视觉样式
app.js                     搜索、筛选、排序与双语阅读器
server.py                  本地静态服务器与健康检查
data/papers.json           可直接部署的数据集
scripts/update_papers.py   OpenAlex 增量同步与可选翻译
scripts/auto_update.sh     带锁和日志的自动更新入口
scripts/install_automation.sh  systemd 用户定时器安装器
tests/                     数据处理单元测试
```
