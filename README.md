<div align="center">

# 📡 广电流量查询

**自托管的中国广电流量查询服务，支持 Docker 一键部署**

[![Docker](https://img.shields.io/badge/Docker-Ready-blue?logo=docker&logoColor=white)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

</div>

---

## ✨ 功能

- 🐳 Docker Compose 一键部署，开箱即用
- 🌐 Web 配置页面，可视化管理请求参数
- 💾 配置持久化，保存在宿主机 `./data/config.json`
- 🔌 简洁的 REST API，方便集成到其他服务

## 🚀 快速开始

### 启动服务

```bash
docker compose up -d --build
```

### 访问

| 地址 | 用途 |
|------|------|
| `http://127.0.0.1:8000/` | 配置管理页面 |
| `http://127.0.0.1:8000/traffic` | 流量查询 API |

### 自定义端口

```bash
APP_PORT=18000 docker compose up -d --build
```

### 停止服务

```bash
docker compose down
```

## ⚙️ 配置"请求配置"

要获取查询所需的请求参数，需通过抓包获取微信小程序的 API 请求：

1. 登录微信小程序 **「广电流量查询」**
2. 打开抓包软件（如 Fiddler、Charles、Reqable 等）
3. 在小程序中触发一次流量查询
4. 在抓包记录中找到以下请求：
   ```
   https://wx.10099.com.cn/contact-web/api/busi/qryUserRes
   ```
5. 复制该请求为 **cURL** 格式，粘贴到配置页面中保存

## 📁 数据持久化

配置文件保存在宿主机，容器重建不会丢失：

```
./data/config.json
```

## 📄 License

MIT
