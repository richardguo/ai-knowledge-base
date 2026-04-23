import type { Plugin } from "@opencode-ai/plugin"
import { statSync, readFileSync } from "fs"
import { join } from "path"

const PROCESSED_DIR = "knowledge/processed"
const VALIDATE_SCRIPT = "hooks/validate_json.py"
const ARTICLES_DIR = "knowledge/articles"

const STATUS_CHECK_INTERVAL_MS = 5000
let lastCheckedTime = 0

function getTodayPrefix(): string {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, "0")
  const day = String(now.getDate()).padStart(2, "0")
  return `${year}-${month}-${day}`
}

async function getTodayJsonFiles(): Promise<string[]> {
  const todayPrefix = getTodayPrefix()
  const files: string[] = []

  try {
    const entries = await Array.fromAsync(
      new Bun.Glob("*.json").scan({ cwd: ARTICLES_DIR })
    )

    for (const name of entries) {
      if (name === "index.json") continue
      if (name.startsWith(todayPrefix)) {
        files.push(`${ARTICLES_DIR}/${name}`)
      }
    }
  } catch {
    return []
  }

  return files
}

function findLatestOrganizerStatus(): string | null {
  try {
    const entries = Array.from(
      new Bun.Glob("organizer-*-status.json").scan({ cwd: PROCESSED_DIR })
    )

    if (entries.length === 0) return null

    let latestFile: string | null = null
    let latestTime = 0

    for (const name of entries) {
      const filePath = join(PROCESSED_DIR, name)
      try {
        const stats = statSync(filePath)
        if (stats.mtimeMs > latestTime) {
          latestTime = stats.mtimeMs
          latestFile = filePath
        }
      } catch {
        continue
      }
    }

    return latestFile
  } catch {
    return null
  }
}

function readStatusFile(filePath: string): { status: string; entries_created: number } | null {
  try {
    const content = readFileSync(filePath, "utf-8")
    return JSON.parse(content)
  } catch {
    return null
  }
}

async function runValidation(
  client: NonNullable<Parameters<Plugin>[0]["client"]>,
  $: NonNullable<Parameters<Plugin>[0]["$"]>
): Promise<void> {
  const files = await getTodayJsonFiles()

  if (files.length === 0) {
    await client.app.log({
      body: {
        service: "article_json_validator",
        level: "info",
        message: "未找到当日生成的 JSON 文件，跳过验证",
      },
    })
    return
  }

  await client.app.log({
    body: {
      service: "article_json_validator",
      level: "info",
      message: `开始 JSON 格式校验 ${files.length} 个当日 JSON 文件`,
    },
  })

  const result = await $`python ${VALIDATE_SCRIPT} ${files.join(" ")}`.quiet()

  if (result.exitCode !== 0) {
    const output = result.stderr.toString() || result.stdout.toString()

    await client.app.log({
      body: {
        service: "article_json_validator",
        level: "error",
        message: `JSON 格式校验失败`,
        extra: { output },
      },
    })

    throw new Error(
      `[article_json_validator] JSON 格式校验失败。\n` +
        `请检查 knowledge/articles 目录下的 JSON 文件格式后重试。\n\n` +
        `${output}`
    )
  }

  await client.app.log({
    body: {
      service: "article_json_validator",
      level: "info",
      message: `JSON 格式校验通过: ${files.length} 个文件全部有效`,
    },
  })
}

export const ArticleJsonValidator: Plugin = async ({ client, $ }) => {
  return {
    "tool.execute.after": async (input, output) => {
      if (input.tool !== "bash") return

      const now = Date.now()
      if (now - lastCheckedTime < STATUS_CHECK_INTERVAL_MS) return

      const command = (input.args?.command as string) || ""
      if (!command.includes("organize.py") && !command.includes("organizer")) return

      lastCheckedTime = now

      await client.app.log({
        body: {
          service: "article_json_validator",
          level: "info",
          message: "检测到 organizer 脚本执行，检查状态文件...",
        },
      })

      await new Promise((resolve) => setTimeout(resolve, 1000))

      const statusFile = findLatestOrganizerStatus()
      if (!statusFile) {
        await client.app.log({
          body: {
            service: "article_json_validator",
            level: "info",
            message: "未找到 organizer 状态文件，跳过验证",
          },
        })
        return
      }

      const statusData = readStatusFile(statusFile)
      if (!statusData || statusData.status !== "completed") {
        await client.app.log({
          body: {
            service: "article_json_validator",
            level: "info",
            message: `organizer 状态为 "${statusData?.status || "unknown"}"，跳过验证`,
          },
        })
        return
      }

      await client.app.log({
        body: {
          service: "article_json_validator",
          level: "info",
          message: `organizer 已完成 (创建了 ${statusData.entries_created} 个条目)，触发 JSON 格式校验`,
        },
      })

      await runValidation(client, $)
    },
  }
}
