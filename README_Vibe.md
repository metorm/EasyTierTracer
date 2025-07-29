这是一个单 python 脚本所构成的工程，启动后，脚本将循环运行，在完成一个周期的任务后进入休眠，等待下一个周期。

刚刚启动后，剧本的行为是：

首先，从.env文件加载各项配置，这个文件与脚本同在一个目录。如果在环境变量中有同名项目，则环境变量优先。

初始化一个 sqlite3 内存数据库，仅存在于内存，不需要磁盘文件。数据库仅需要一张表，各列为：

+ id，主机ID，整数（主键）
+ hostname，主机名，字符串
+ ip，IP 地址，字符串
+ loss_rate，丢包率，浮点数
+ version，客户端版本，字符串

每个周期的任务为：

执行 EASY_TIER_PEER_COMMAND 变量所指定的命令，保存命令所生成的输出结果，其结果应该是类似如下的json字符串：

```
[
  {
    "cidr": "6.6.6.2/24",
    "ipv4": "6.6.6.2",
    "hostname": "H1",
    "cost": "Local",
    "lat_ms": "-",
    "loss_rate": "-",
    "rx_bytes": "-",
    "tx_bytes": "-",
    "tunnel_proto": "-",
    "nat_type": "PortRestricted",
    "id": "3687869683",
    "version": "2.3.2-42c98203"
  },
  {
    "cidr": "6.6.6.89/24",
    "ipv4": "6.6.6.89",
    "hostname": "H1",
    "cost": "p2p",
    "lat_ms": "7.055",
    "loss_rate": "0.000",
    "rx_bytes": "10.95 kB",
    "tx_bytes": "46.31 kB",
    "tunnel_proto": "udp",
    "nat_type": "Symmetric",
    "id": "2425623759",
    "version": "2.3.2-42c98203"
  },
  {
    "cidr": "6.6.6.1/24",
    "ipv4": "6.6.6.1",
    "hostname": "H3",
    "cost": "p2p",
    "lat_ms": "6.083",
    "loss_rate": "0.000",
    "rx_bytes": "8.89 kB",
    "tx_bytes": "77.08 kB",
    "tunnel_proto": "tcp",
    "nat_type": "PortRestricted",
    "id": "1524885746",
    "version": "2.3.2-42c98203"
  },
  {
    "cidr": "6.6.6.9/24",
    "ipv4": "6.6.6.9",
    "hostname": "H4",
    "cost": "p2p",
    "lat_ms": "18.297",
    "loss_rate": "0.000",
    "rx_bytes": "11.21 kB",
    "tx_bytes": "52.87 kB",
    "tunnel_proto": "tcp",
    "nat_type": "PortRestricted",
    "id": "922710975",
    "version": "2.3.2-42c98203"
  },
  {
    "cidr": "6.6.6.80/24",
    "ipv4": "6.6.6.80",
    "hostname": "H5",
    "cost": "p2p",
    "lat_ms": "5.681",
    "loss_rate": "0.000",
    "rx_bytes": "13.92 kB",
    "tx_bytes": "23.33 kB",
    "tunnel_proto": "udp",
    "nat_type": "Symmetric",
    "id": "307294935",
    "version": "2.3.2-42c98203"
  },
  {
    "cidr": "6.6.6.90/24",
    "ipv4": "6.6.6.90",
    "hostname": "H6",
    "cost": "p2p",
    "lat_ms": "3.445",
    "loss_rate": "0.000",
    "rx_bytes": "39.08 kB",
    "tx_bytes": "88.94 kB",
    "tunnel_proto": "udp,tcp",
    "nat_type": "PortRestricted",
    "id": "2339083907",
    "version": "2.3.2-42c98203"
  }
]
```

从中解析每一个对象，只需要读取数据库表中需要的字段。需要一个class来保存这些数据。这个class应该具备的函数包括：

+ 从json数据中初始化自身
+ 从数据库的某一行初始化自身
+ 保存自身到数据库
+ 对比自身与一个同类的对象，返回差异描述文本
+ 生成自身简述文本

解析后，从数据库中查询该设备是否已经存在，如果存在，则对比各个字段，生成差异描述文本。其中，“丢包率”仅在新旧数值中至少一个一个大于0.02，且相对变化量（新旧数值中较大者为分母）大于 5% 时才认为有差异。

解析JSON时注意给出的JSON中数据类型全是字符串，但我们需要把某些字段转为数字。

对于新增的机器，生成的这段变化描述应该注明这是“新上线机器”。对于数据库中存在，但现在不存在的机器，应注明是“刚刚下线”。

将所有的变化的描述，保存到一个字符串中。如果没有任何变化，则这个字符串应该是空的。

使用 WEB_HOOK_TEMPLATE 变量所给出的模板，将模板中的`{{ ETT_MSG }}`替换为改变描述，生成最终的 WEB_HOOK_URL。使用 GET 方法向 WEB_HOOK_URL 发送请求，如果返回码是 200，则说明发送成功，否则在控制台中打印错误信息。

无论成败，等待 CHECK_INTERVAL_SECONDS 秒之后重复上面的过程，除非进程被强制打断。

额外地，如果当前时间与 DAILY_REPORT_TIME 时间的差异（正负均可）小于 REPORT_TIME_DIFF_SECONDS 秒，则本次循环后额外发送一条消息，内容是当前所有设备的描述。

循环最后，清空数据表，将本次循环新解析的数据存入数据库，等待 CHECK_INTERVAL_SECONDS 时间后继续循环。

整个过程使用logging模块记录日志。