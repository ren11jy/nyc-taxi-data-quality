# NYC Taxi Data Quality Pipeline

一个使用 Python、pandas、Great Expectations (GX Core) 和 SQLite 的数据质量项目。程序读取纽约出租车样例数据，运行质量规则；通过校验的数据写入 SQLite，失败批次不入库，并导出异常行。

## 数据来源

- [GX 官方教程提供的 2019 年 1 月黄色出租车 CSV 样例](https://raw.githubusercontent.com/great-expectations/gx_tutorials/main/data/yellow_tripdata_sample_2019-01.csv)，共 10,000 行。首次运行时自动下载到 `data/`，之后使用本地副本。
- 样例源自 [纽约市 TLC 出租车行程公开数据](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page)。本项目使用的是 GX 教程处理过的样例，字段名与 TLC 原始 Parquet 文件不同。

## 环境与运行

需要 Python 3.13 或 3.14。以下命令在项目根目录执行；Windows PowerShell 可直接调用虚拟环境中的 Python，无需激活。

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe .\validate.py
```

如果使用其他可用的 Python 版本，替换第一行的 `py -3.14`。正常批次返回退出码 `0`，质量规则失败返回 `1`，程序或下载出错返回 `2`。

运行两个故意注入异常的场景：

```powershell
.\.venv\Scripts\python.exe .\validate.py --inject-error
.\.venv\Scripts\python.exe .\validate.py --inject-time-error
```

这两个命令返回 `1` 是预期行为。`--inject-error` 将第一行行程距离改为 `-1`；`--inject-time-error` 将第一行下车时间改为比上车时间早一分钟。注入仅修改内存中的 DataFrame，不改动本地样例 CSV。

## 质量规则与输出

GX Expectation Suite 检查上车和下车时间非空、行程距离不为负、乘客数在 1～6 之间，以及可解析的行程时长不为负。时间差由 pandas 计算，单位为分钟。

| 运行方式 | 结果文件 | 数据处理 |
| --- | --- | --- |
| 正常 | `reports/normal.json` | 10,000 行写入 `data/validated_taxi.sqlite` 的 `validated_trips` 表 |
| 负距离注入 | `reports/invalid.json`、`reports/invalid_rows.csv` | 导出异常行，不写入数据库 |
| 时间倒置注入 | `reports/invalid_time.json`、`reports/invalid_time_rows.csv` | 导出异常行，不写入数据库 |

每次成功校验会替换 SQLite 表，避免重复运行造成重复行。JSON 包含 GX 的逐规则校验结果；异常 CSV 增加 `failure_reason` 列。`data/` 和 `reports/` 是运行产物，不提交到 Git。

## 自动校验

GitHub Actions 工作流位于 `.github/workflows/validate.yml`。它运行正常批次和时间异常批次，检查异常批次被拒绝，同时确认数据库仍保留正常批次的 10,000 行。

## 项目边界

这是可复现的本地数据质量演示，使用 10,000 行样例和人为注入的错误。它尚未对完整月份数据做批量处理，也未部署到生产环境。真实数据的阈值和例外情况需要结合业务口径重新确定。
