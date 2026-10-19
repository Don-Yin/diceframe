import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import GameLorebookSelectionDialog from "../src/components/play/GameLorebookSelectionDialog.vue";
import { i18n } from "../src/i18n";

const mocks = vi.hoisted(() => ({ api: vi.fn() }));
vi.mock("../src/api/client", () => ({
  api: mocks.api,
  errorMessage: (cause: unknown) => String((cause as Error)?.message || cause),
}));
vi.mock("../src/composables/useToast", () => ({
  useToast: () => ({
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  }),
}));
describe("GameLorebookSelectionDialog", () => {
  beforeEach(() => {
    mocks.api.mockReset();
    i18n.global.locale.value = "zh-CN";
    mocks.api.mockResolvedValue({
      ok: true,
      game_key: "g/1",
      world_id: "w1",
      world_name: "城堡",
      mode: "explicit",
      max_books: 16,
      books: [
        {
          id: "a",
          name: "主线",
          enabled: true,
          entry_count: 2,
          selected: true,
        },
        {
          id: "b",
          name: "角色",
          enabled: true,
          entry_count: 1,
          selected: false,
          locked: true,
        },
      ],
    });
  });
  it("loads game/world and excludes locked books from changes", async () => {
    mount(GameLorebookSelectionDialog, {
      props: { open: true, gameKey: "g/1" },
      attachTo: document.body,
      global: { plugins: [i18n] },
    });
    await flushPromises();
    expect(document.body.textContent).toContain("城堡");
    expect(document.body.textContent).toContain("主线");
    expect(document.body.textContent).toContain("2 条");
    expect(document.body.textContent).not.toContain("0 ·");
    const boxes = [...document.querySelectorAll('input[type="checkbox"]')];
    expect(boxes[1].hasAttribute("disabled")).toBe(true);
    mocks.api.mockResolvedValueOnce({
      ok: true,
      session_id: "s1",
      approval: {
        approval_id: "a1",
        plan_digest: "d1",
        label: "设置",
        preview: { target_name: "城堡", books: [{ id: "a", name: "主线" }] },
      },
    });
    (
      document.querySelector(
        '[data-testid="lorebook-save"]',
      ) as HTMLButtonElement
    ).click();
    await flushPromises();
    expect(
      mocks.api.mock.calls.some(([path]) => path === "/assistant/agent/plan"),
    ).toBe(true);
  });
  it("explains an empty editable selection while preserving character sources", async () => {
    mocks.api.mockResolvedValueOnce({
      ok: true,
      game_key: "g/1",
      world_id: "w1",
      world_name: "城堡",
      mode: "explicit",
      max_books: 16,
      books: [],
    });
    mocks.api.mockResolvedValueOnce({
      ok: true,
      session_id: "s1",
      approval: {
        approval_id: "a1",
        plan_digest: "d1",
        label: "设置",
        preview: { target_name: "城堡", books: [] },
      },
    });
    mount(GameLorebookSelectionDialog, {
      props: { open: true, gameKey: "g/1" },
      attachTo: document.body,
      global: { plugins: [i18n] },
    });
    await flushPromises();
    (
      document.querySelector(
        '[data-testid="lorebook-save"]',
      ) as HTMLButtonElement
    ).click();
    await flushPromises();
    expect(document.body.textContent).toContain(
      "本局不使用可编辑资料册，角色资料仍保留",
    );
  });
  it("cancels a stale plan after switching game identity", async () => {
    let resolvePlan!: (value: unknown) => void;
    mocks.api
      .mockImplementationOnce(() =>
        Promise.resolve({
          ok: true,
          game_key: "g/1",
          world_id: "w1",
          world_name: "城堡",
          mode: "explicit",
          max_books: 16,
          books: [
            {
              id: "a",
              name: "主线",
              enabled: true,
              entry_count: 1,
              selected: true,
            },
          ],
        }),
      )
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolvePlan = resolve;
          }),
      )
      .mockResolvedValue({
        ok: true,
        game_key: "g/2",
        world_id: "w2",
        world_name: "港口",
        mode: "explicit",
        max_books: 16,
        books: [],
      });
    const wrapper = mount(GameLorebookSelectionDialog, {
      props: { open: true, gameKey: "g/1" },
      attachTo: document.body,
      global: { plugins: [i18n] },
    });
    await flushPromises();
    (
      document.querySelector(
        '[data-testid="lorebook-save"]',
      ) as HTMLButtonElement
    ).click();
    await flushPromises();
    await wrapper.setProps({ gameKey: "g/2" });
    resolvePlan({
      ok: true,
      session_id: "old-s",
      approval: {
        approval_id: "old-a",
        plan_digest: "old-d",
        preview: { target_name: "旧局", books: [] },
      },
    });
    await flushPromises();
    const cancel = mocks.api.mock.calls.find(
      ([path, init]) =>
        path === "/assistant/agent/confirm" &&
        JSON.parse(init.body).session_id === "old-s",
    );
    expect(cancel).toBeTruthy();
    expect(JSON.parse(cancel![1].body).approved).toBe(false);
    expect(wrapper.emitted("changed")).toBeUndefined();
  });
});
