# 首次配置后双击启动

此交付包面向Windows x64和macOS Apple Silicon。它包含DocTransAI源码、自有渲染器、启动/自检脚本和锁定的Python依赖；不包含密钥、业务样本或Codex文件。Windows-x64交付包附带已校验的官方Python/uv启动归档，首次安装无需再从GitHub下载Python；Python业务依赖仍从PyPI按uv.lock安装，LibreOffice需预先安装。源码ZIP或git clone未附带二进制启动归档，会自动尝试联网下载。它不是完全离线免安装包。

## Windows

1. 从LibreOffice官网安装Writer和Calc，推荐使用本版验收的26.8.1。标准路径 `C:\Program Files\LibreOffice\program\soffice.com` 会自动识别。不要依赖Microsoft Office或Codex。
2. 将交付ZIP解压到有写入权限的目录（例如用户文档目录），不要直接在ZIP里双击，也不要放进Program Files。
3. 双击 `setup-windows.cmd`。脚本优先使用包内runtime/bootstrap中的官方uv/Python归档并校验SHA256，安装到本目录runtime；未附带归档时从官方来源下载。随后准备uv.lock锁定的业务依赖。首次生成.env，不覆盖已有配置。
4. 按提示打开 `outputs/setup-check-*/` 的DOCX/XLSX PNG自检图，确认中文、表格可见。Windows推荐安装有授权的微软雅黑/宋体，或使用开源Noto Sans CJK；原模板专用字体缺失仍会发生替换。
5. 用记事本打开 `.env`，填写DataProxy地址与授权Key、LLM地址与Key。默认模型为kimi-k3。配置文件不能上传GitHub或发到公开群。
6. 双击 `start-windows.cmd`，浏览器会打开本机测试页。保持窗口打开；Ctrl+C停止服务。再次启动会打开已运行页面，不重复启动任务。

PowerShell执行权限仅在setup包装命令的当前进程使用Bypass，不修改系统或用户的持久执行策略。公司设备若禁止脚本/安装，请由管理员安装依赖，不绕过组织策略。首次安装的下载需要访问GitHub/Python分发和PyPI；失败会报错，修复网络后再次运行setup，不自动改用不明来源。Python下载超过3分钟会终止本次下载进程并说明原因。网络受限时，管理员可从Astral官方python-build-standalone取得Windows x64 Python 3.12.13的install_only归档，在另一台可联网电脑下载校验后，将其中python目录放到本目录runtime/python（应存在python.exe），再运行setup。脚本校验解释器版本，不使用任意未知Python。

## macOS

1. 从LibreOffice官网安装macOS对应架构版本，放入 `/Applications` 或 `~/Applications`。
2. 解压交付包，双击 `setup-macos.command`；首次完成Python与依赖安装、自检并创建.env。
3. 填写.env中的服务地址和Key，检查生成的中文预览。
4. 双击 `start-macos.command`。如果解压工具丢失可执行权限，在终端执行 `chmod +x setup-macos.command start-macos.command`。系统若要求确认来源，按系统提示核实后操作，不关闭系统安全保护。

macOS使用系统中文字体，例如苹方；跨系统模板的字体不同，分页可能不同。交付之前仍应目检成品，不能把文本提取成功等同于版式正确。

## 用户实际要填什么

默认渲染器与Python路径已经自动定位，通常只需填写：

```dotenv
DOCTRANSAI_DATAPROXY_BASE_URL=https://dataproxy.example.com
DOCTRANSAI_DATAPROXY_API_KEY=replace-with-project-key
DOCTRANSAI_LLM_BASE_URL=https://provider.example/v1
DOCTRANSAI_LLM_API_KEY=replace-with-model-key
DOCTRANSAI_LLM_MODEL=kimi-k3
```

部署方指定公网HTTP时，另将 `DOCTRANSAI_DATAPROXY_ALLOWED_HTTP_ORIGIN` 填为同一个准确origin。只对批准的部署显式允许，不关闭其他地址的HTTPS限制。

LibreOffice非标准路径可配置 `DOCTRANSAI_SOFFICE`，例如 `C:/Tools/LibreOffice/program/soffice.com`。从旧版迁移时，删除或注释指向另一台电脑的 `DOCTRANSAI_DOCX_RENDERER`、`DOCTRANSAI_RENDER_PYTHON`，即可启用项目内置渲染器。显式外部渲染器仍可用于兼容旧环境。

## 自检与故障定位

```bash
uv run doctransai doctor --env-file .env --require-credentials
uv run doctransai doctor --env-file .env --render-check outputs/new-check
uv run doctransai render template.docx --output-dir outputs/new-preview --emit-pdf
uv run doctransai web --env-file .env --port 8765
```

`doctor`不显示密钥、不调用远端服务；配置齐全不代表远端连通。render-check必须使用新目录，并只生成合成自检资料。启动页端口被其他程序占用会明确报错，可用 `start-windows.cmd --port 8766` 或 `./start-macos.command --port 8766` 改端口。

出现找不到LibreOffice时先安装或指定可执行文件。出现中文缺字先检查字体；出现配置未就绪先替换.env占位符；出现拒绝连接先确认启动窗口未关闭。窗口或机器关闭不会自动恢复正在转换的任务，历史文件仍在outputs/web中。

## 渲染与依赖边界

项目自己的 `src/doctransai/render_document.py` 使用LibreOffice生成PDF，再由pypdfium2/PDFium生成PNG；PDFium通过锁定的Python wheel安装，默认路径不需要Poppler、pdf2image或Codex。每次Office转换使用独立临时副本及用户profile，不覆盖源文件；超时停止本次进程。PDF输入直接光栅化，无需LibreOffice。

Python固定3.12.13，pypdfium2固定5.14.0，其余Python库见uv.lock。LibreOffice和字体属于操作系统依赖，本包不重分发Microsoft字体；Windows启动归档保持官方分发的Python/uv许可文件，解压后仍保留。pypdfium2/PDFium及其依赖许可随官方wheel保留；LibreOffice从官方安装，遵循其许可。项目渲染器独立编写，未复制Codex bundled脚本。

## 打包

在干净的公开源码仓库执行 `python scripts/build_desktop_bundle.py`，得到 `dist/DocTransAI-<版本>-desktop.zip` 和SHA256。包内delivery-manifest.json记录源码提交、逐文件哈希与是否为未提交验证构建。生成器按白名单打包，不收录.env、输出、实验数据、Git历史或业务样本。可追加 `--windows-bootstrap <已校验的启动归档目录>` 构建包含Python/uv归档的Windows-x64包，构建器再次检查固定SHA256。密钥须单独分发，不能塞入ZIP。

## 当前验证状态

开发验证已在macOS Apple Silicon、Python 3.12.13、LibreOffice 26.8.1.1、PDFium 5.14.0下完成解压包首次安装、中文DOCX/XLSX渲染及真实ZIP模式转换/审计/下载；仍需按发布记录确认Windows原生端到端验收，不能仅凭跨平台脚本或模拟测试宣布所有Windows环境可用。
