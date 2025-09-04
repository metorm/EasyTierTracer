# EasyTierTracer


追踪和提示 Easy Tier 私网中的设备变化，及时掌握设备在线情况，并在入侵发生时马上得到报告。

# 安装和运行

```
pip install -i https://mirrors.ustc.edu.cn/pypi/simple requests
pip install -i https://mirrors.ustc.edu.cn/pypi/simple dotenv
```

在.env文件中，配置pushplus的凭证，或者修改为其他webhook.

# Windows 下安装为服务

在 EasyTierTracerSrv.xml 中配置适当的绝对路径。

从 https://github.com/winsw/winsw/releases 下载 winsw，放置在项目目录中，重命名为 EasyTierTracerSrv.exe，管理员终端执行：

```
.\EasyTierTracerSrv.exe install
.\EasyTierTracerSrv.exe start
```