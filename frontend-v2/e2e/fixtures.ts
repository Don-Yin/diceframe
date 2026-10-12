import { expect, test as base } from '@playwright/test'
import { prepareAuthenticatedPage } from './support'

export const test = base.extend({
  page: async ({ page, request }, use) => {
    await prepareAuthenticatedPage(page, request)
    await use(page)
  },
})

export { expect }
