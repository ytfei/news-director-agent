/**
 * 极简 Markdown 渲染：只处理写作产出的 `# / ##` 与段落。
 *
 * 不引第三方库 —— 成稿结构是自己拼的（后端 `assemble_markdown`），
 * 不需要通用 Markdown 解析器，引一个反而带来 XSS 面与体积。
 */
export function Markdown({ text, className }: { text: string; className?: string }) {
  const blocks = text.split(/\n{2,}/)
  return (
    <div className={className ?? 'space-y-3'}>
      {blocks.map((b, i) => {
        if (b.startsWith('## '))
          return (
            <h2 key={i} className="mt-4 text-sm font-semibold text-slate-900">
              {b.slice(3)}
            </h2>
          )
        if (b.startsWith('# '))
          return (
            <h1 key={i} className="text-base font-semibold text-slate-900">
              {b.slice(2)}
            </h1>
          )
        return (
          <p key={i} className="text-[13px] leading-7 text-slate-700">
            {b}
          </p>
        )
      })}
    </div>
  )
}
