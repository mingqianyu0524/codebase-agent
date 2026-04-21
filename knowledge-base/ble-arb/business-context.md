# HMOS AI Engine — BLE 协同仲裁模块 Business Context

## 概述

本模块是 HarmonyOS AI Engine 的一部分，负责通过蓝牙 BLE 广播（Advertising）实现
多设备间的协同仲裁（Collaborative Arbitration）。仲裁决定哪台设备在特定时间段内
拥有某项资源的执行权（如 AI 推理任务、传感器采样主权）。

## BLE 广播基础

- **BLE Advertising**：设备周期性广播数据包，无需配对即可被其他设备扫描接收。
- **ADV_IND / ADV_NONCONN_IND**：不可连接广播类型，适合仲裁信令的单向广播。
- **广播数据格式**：AD Structure（Length + Type + Data），可在 Manufacturer Specific
  Data 字段中携带自定义仲裁载荷。
- **广播间隔（Advertising Interval）**：影响信令延迟与功耗的关键参数。
- **RSSI**：接收信号强度，可用于估算设备距离，辅助仲裁决策。

## 协同仲裁核心概念

- **Arbitration Token**：代表执行权的逻辑令牌，通过 BLE 广播在设备间竞争和传递。
- **Priority / Weight**：每个节点的仲裁优先级，可能根据设备状态动态调整。
- **Epoch / Round**：仲裁周期，定时触发一轮竞争流程。
- **Consensus**：多节点就某一决定（谁获得 token）达成一致的过程。
- **Heartbeat**：设备通过 BLE 广播周期性声明在线状态，超时则视为离线。

## 代码质量说明

本代码仓注释稀少，部分模块缺乏文档说明。标注时需综合利用：
1. 函数和变量命名推断设计意图
2. BLE 协议背景知识
3. Codebase-Memory 提供的调用关系图
4. 业务逻辑上下文

**请在标注中明确指出哪些描述是推断（inferred），哪些有代码或命名直接支撑。**

## 技术栈

- **语言**：TypeScript
- **运行环境**：HarmonyOS / ArkTS runtime
- **BLE API**：HarmonyOS `@ohos.bluetooth.ble` 系统 API
- **构建工具**：待 cbm index 后补充

## 目录结构

> 待 `codebase-memory-mcp cli index_repository` 完成后，通过 `--discover` 补充。

## 命名约定（待观察后补充）

- 命名模式、常见前缀/后缀等，请在标注过程中逐步归纳并更新此处。
