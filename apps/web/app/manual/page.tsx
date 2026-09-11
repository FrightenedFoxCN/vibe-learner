import type { Metadata } from "next";
import { AppLink } from "../../lib/app-navigation";
import { TopNav } from "../../components/top-nav";
import styles from "./page.module.css";

export const metadata: Metadata = {
  title: "用户手册 · Vibe Learner",
  description: "从第一次生成计划到章节学习、角色互动与问题恢复。",
};

const chapters = [
  ["start", "快速开始"],
  ["study", "计划与学习"],
  ["characters", "角色与场景"],
  ["tavern", "角色酒馆"],
  ["recovery", "遇到问题"],
  ["data", "数据与隐私"],
  ["install", "桌面安装"],
] as const;

export default function ManualPage() {
  return (
    <main className={`with-app-nav ${styles.page}`}>
      <TopNav currentPath="/manual" />
      <div className={styles.content}>
        <header className={styles.header} id="manual-top">
          <AppLink path="/" className={styles.back}>← 返回首页</AppLink>
          <p className={styles.eyebrow}>使用指南</p>
          <h1>用户手册</h1>
          <p>先生成计划，再开始对话。也可以直接进入酒馆，与角色自由交流。</p>
        </header>

        <nav aria-label="手册目录" className={styles.contents}>
          {chapters.map(([id, title], index) => (
            <a key={id} href={`#${id}`}><span>0{index + 1}</span>{title}</a>
          ))}
        </nav>

        <section id="start" className={styles.section} aria-labelledby="start-title">
          <h2 id="start-title">01 · 快速开始</h2>
          <ol>
            <li>打开 <AppLink path="/settings">统一设置</AppLink>。先试用可选“本地模拟”（mock），无需模型密钥；回复是模拟内容。</li>
            <li>打开 <AppLink path="/plan">计划生成</AppLink>，选择“仅学习目标”，输入具体目标，例如“用一周掌握 Python 循环，每天 30 分钟”，点击“按目标生成”。</li>
            <li>查看计划，创建并打开章节对话，选择学习单元后开始提问。</li>
          </ol>
          <p className={styles.note}>使用真实模型：在统一设置选择“LiteLLM SDK”，填写服务商提供的模型名、API Key 和连接地址，确认“已保存”后再生成。可拉取模型与能力；拉取不到时按服务商信息手填。真实调用可能产生费用。</p>
          <p>桌面版首次启动若进入设置，请先按提示创建或解锁密钥保险库（Vault）。</p>
        </section>

        <section id="study" className={styles.section} aria-labelledby="study-title">
          <h2 id="study-title">02 · 计划与学习</h2>
          <ul>
            <li><strong>有教材：</strong>在计划生成选择“教材 + 目标”，上传 PDF，填写目标后生成。扫描件需要 OCR，处理时间通常更长。</li>
            <li><strong>没有教材：</strong>使用“仅学习目标”；这类计划没有教材页码可供查阅。</li>
            <li><strong>检查计划：</strong>确认学习单元与排期。可从计划历史切换已有计划。</li>
            <li><strong>开始学习：</strong>在 <AppLink path="/study">章节对话</AppLink> 选择计划并创建或打开会话。切换学习排期以学习其他单元，点击引用查看对应教材页。</li>
            <li><strong>回答互动题：</strong>选择或填写答案后提交，等待结果显示再继续。未显示结果时先查询，不要重复提交。</li>
          </ul>
          <p className={styles.note}>模型回答和 OCR 识别可能有误，关键内容请对照原文。计划的整体修订、差异确认与回滚尚未提供。</p>
        </section>

        <section id="characters" className={styles.section} aria-labelledby="characters-title">
          <h2 id="characters-title">03 · 角色与场景</h2>
          <ul>
            <li><AppLink path="/persona-spectrum">人格色谱</AppLink>：编辑教师的风格、背景与行为，保存后在计划或酒馆中选择。模型辅助生成的内容请先检查。</li>
            <li><AppLink path="/scene-setup">场景搭建</AppLink>：添加地点、层级和物体，保存到场景库后选用。场景是可选项；删除前确认影响范围。</li>
            <li><AppLink path="/sensory-tools">感官工具</AppLink>：查看和调整对话可用工具。初次使用可保留默认配置。</li>
          </ul>
          <p>修改人格后，已有酒馆房间仍保留创建时的人格快照；要使用新设定，请创建新房间。</p>
        </section>

        <section id="tavern" className={styles.section} aria-labelledby="tavern-title">
          <h2 id="tavern-title">04 · 角色酒馆</h2>
          <ol>
            <li>打开 <AppLink path="/tavern">角色酒馆</AppLink>，选择已保存的人格，可选场景，创建房间。</li>
            <li>选择本轮回复角色，输入消息；需要引导讨论时，补充下一轮指导。</li>
            <li>发送后等待回复。多人回复会依次产生，已完成内容会保留。</li>
          </ol>
          <p>部分角色未完成时，按页面提示恢复或定向重试。被阻塞的角色尚未完成执行，不等于角色生成失败。停止后不再接收本次生成的新结果，但上游模型可能仍在计算或计费。</p>
          <p>可在最近房间中继续对话；归档的房间需恢复后再使用。酒馆记录与章节学习会话分开保存。</p>
        </section>

        <section id="recovery" className={styles.section} aria-labelledby="recovery-title">
          <h2 id="recovery-title">05 · 遇到问题</h2>
          <dl>
            <dt>超时、断网，或提示结果未确认</dt>
            <dd>恢复连接，回到原会话或房间，使用页面提供的查询或恢复操作。结果未确认前不要重发；仅在明确允许重试时重试。</dd>
            <dt>教材解析或计划生成失败</dt>
            <dd>先查看错误提示，确认 PDF 能正常打开、服务连接正常。大型扫描件可先拆分为较小文件再处理。</dd>
            <dt>设置未保存或模型无法连接</dt>
            <dd>在统一设置检查模型、地址和密钥；保存失败时点击“重试保存”，等到“已保存”。网页版还需确认后端服务已启动。</dd>
            <dt>需要排查调用或反馈问题</dt>
            <dd>在 <AppLink path="/model-usage">用量审计</AppLink> 查看调用与 Token；实际费用以服务商账单为准。通过全局 Debug 查看详细错误，分享记录前检查敏感信息。</dd>
          </dl>
        </section>

        <section id="data" className={styles.section} aria-labelledby="data-title">
          <h2 id="data-title">06 · 数据与隐私</h2>
          <p>学习记录默认保存在本机。使用真实模型时，相关教材片段、对话和角色设定会发送给所配置的服务商。</p>
          <ul>
            <li><strong>源码运行：</strong>默认数据目录为 <code>services/ai/data/</code>；自定义部署以实际配置为准。</li>
            <li><strong>桌面版：</strong>业务数据位于系统应用数据目录下的 <code>ai-data</code>，密钥由独立 Vault 保存。</li>
            <li><strong>备份：</strong>退出应用并停止后端后，备份完整数据目录；桌面版一并备份应用数据目录。只复制 PDF 或 JSON 不等于完整备份。</li>
            <li><strong>留存：</strong>归档不等于删除。删除页面记录也不代表所有调试制品或服务商副本已清除；清理目录前先备份。部分编辑草稿保存在浏览器本地，清除站点数据可能丢失草稿。</li>
          </ul>
        </section>

        <section id="install" className={styles.section} aria-labelledby="install-title">
          <h2 id="install-title">07 · 桌面安装</h2>
          <p>从项目发布页下载适合系统和芯片架构的安装包，并将文件 SHA-256 与同次发布提供的校验值逐字比较；不一致时重新下载。</p>
          <ul>
            <li><strong>macOS（DMG）：</strong>打开镜像，将应用拖入“应用程序”后启动。</li>
            <li><strong>Windows（NSIS / .exe）：</strong>运行安装程序，按提示完成安装。</li>
            <li><strong>Linux（AppImage）：</strong>在文件属性中允许作为程序执行，再打开文件。</li>
          </ul>
          <details>
            <summary>如何计算 SHA-256</summary>
            <p>在终端或 PowerShell 中将文件名替换为实际下载路径：</p>
            <p>macOS：<code>shasum -a 256 "安装包.dmg"</code></p>
            <p>Windows：<code>Get-FileHash "安装包.exe" -Algorithm SHA256</code></p>
            <p>Linux：<code>sha256sum "安装包.AppImage"</code></p>
          </details>
          <p className={styles.note}>预览包可能未签名或未经公证，系统可能拦截；macOS 的临时签名不等于正式公证。请核实来源并遵循系统安全提示。生产签名及跨平台安装验收仍在完善；未打包 OCR 模型的版本不保证离线识别扫描件。</p>
        </section>

        <footer className={styles.footer}>
          <AppLink path="/plan">开始生成计划 →</AppLink>
          <a href="#manual-top">回到顶部 ↑</a>
        </footer>
      </div>
    </main>
  );
}
