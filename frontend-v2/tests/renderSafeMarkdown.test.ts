import { describe, expect, it } from 'vitest'

import { renderSafeMarkdown } from '../src/utils/markdown'

describe('renderSafeMarkdown', () => {
  it('renders markdown for announcement content', () => {
    const html = renderSafeMarkdown('# 公告\n\n第一行公告内容。')
    expect(html).toContain('公告')
    expect(html).toContain('第一行公告内容')
  })

  it('strips dangerous HTML from announcement content', () => {
    const html = renderSafeMarkdown(
      '# 公告\n<script>alert("x")</script>\n<img src="x" onerror="alert(1)">\n<a href="javascript:alert(1)">bad</a>',
    )
    expect(html).not.toContain('<script')
    expect(html).not.toContain('onerror')
    expect(html).not.toContain('javascript:')
    expect(html).toContain('公告')
  })
})
