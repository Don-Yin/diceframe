import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import LorebookRecoveryDialog from "../src/features/lorebook/LorebookRecoveryDialog.vue";
import { i18n } from "../src/i18n";

const mocks = vi.hoisted(() => ({
  api: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
}));
vi.mock("../src/api/client", () => ({
  api: mocks.api,
  errorMessage: (cause: unknown) => String((cause as Error)?.message || cause),
}));
vi.mock("../src/composables/useToast", () => ({
  useToast: () => ({
    success: mocks.success,
    error: mocks.error,
    info: vi.fn(),
    warning: vi.fn(),
  }),
}));

describe("LorebookRecoveryDialog", () => {
  beforeEach(() => {
    mocks.api.mockReset();
    mocks.success.mockReset();
    mocks.error.mockReset();
    i18n.global.locale.value = "zh-CN";
    mocks.api.mockResolvedValue({
      ok: true,
      operations: [
        {
          operation_id: "op-1",
          kind: "delete",
          label: "删除资料册",
          target_name: "旧资料册",
          target_count: 3,
          created_at: "2026-10-14T00:00:00Z",
          status: "completed",
          can_undo: true,
          can_restore: true,
        },
      ],
    });
  });
  it("loads bounded history and requires a second confirm before confirm endpoint", async () => {
    mount(LorebookRecoveryDialog, {
      props: { open: true },
      attachTo: document.body,
      global: { plugins: [i18n] },
    });
    await flushPromises();
    expect(document.body.textContent).toContain("旧资料册");
    mocks.api.mockResolvedValueOnce({
      ok: true,
      session_id: "s1",
      approval: {
        approval_id: "a1",
        plan_digest: "d1",
        label: "恢复",
        preview: { target_name: "旧资料册", target_count: 3 },
      },
    });
    await (
      document.querySelector(
        '[data-testid="recovery-undo-op-1"]',
      ) as HTMLButtonElement
    ).click();
    await flushPromises();
    expect(document.body.textContent).toContain("请确认这次内容恢复");
    expect(
      mocks.api.mock.calls.some(
        ([path]) => path === "/assistant/agent/confirm",
      ),
    ).toBe(false);
    (
      document.querySelector(
        '[data-testid="recovery-confirm"]',
      ) as HTMLButtonElement
    ).click();
    await flushPromises();
    expect(
      mocks.api.mock.calls.some(
        ([path, init]) =>
          path === "/assistant/agent/confirm" && init.method === "POST",
      ),
    ).toBe(true);
  });
  it("keeps a failed load retryable", async () => {
    mocks.api.mockRejectedValueOnce(new Error("offline"));
    mount(LorebookRecoveryDialog, {
      props: { open: true },
      attachTo: document.body,
      global: { plugins: [i18n] },
    });
    await flushPromises();
    expect(document.body.textContent).toContain("offline");
    mocks.api.mockResolvedValueOnce({ ok: true, operations: [] });
    (
      document.querySelector(
        '[data-testid="recovery-retry"]',
      ) as HTMLButtonElement
    ).click();
    await flushPromises();
    expect(document.body.textContent).toContain("暂无可回收");
  });
  it("cancels a plan that resolves after the dialog identity closes", async () => {
    let resolvePlan!: (value: unknown) => void;
    mocks.api
      .mockImplementationOnce(() =>
        Promise.resolve({
          ok: true,
          operations: [
            {
              operation_id: "op-1",
              kind: "delete",
              label: "删除",
              target_name: "旧",
              target_count: 1,
              created_at: "",
              status: "completed",
              can_undo: true,
              can_restore: false,
            },
          ],
        }),
      )
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolvePlan = resolve;
          }),
      );
    const wrapper = mount(LorebookRecoveryDialog, {
      props: { open: true },
      attachTo: document.body,
      global: { plugins: [i18n] },
    });
    await flushPromises();
    (
      document.querySelector(
        '[data-testid="recovery-undo-op-1"]',
      ) as HTMLButtonElement
    ).click();
    await flushPromises();
    await wrapper.setProps({ open: false });
    resolvePlan({
      ok: true,
      session_id: "old-s",
      approval: {
        approval_id: "old-a",
        plan_digest: "old-d",
        preview: { target_name: "旧" },
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
  it("shows prepared operations as pending verification and blocks repeat actions", async () => {
    mocks.api.mockResolvedValueOnce({
      ok: true,
      operations: [
        {
          operation_id: "prepared-1",
          kind: "delete",
          label: "待核实",
          target_name: "资料册",
          target_count: 1,
          created_at: "",
          status: "prepared",
          can_undo: true,
          can_restore: true,
        },
      ],
    });
    mount(LorebookRecoveryDialog, {
      props: { open: true },
      attachTo: document.body,
      global: { plugins: [i18n] },
    });
    await flushPromises();
    expect(document.body.textContent).toContain("结果待核实");
    expect(
      document.querySelector('[data-testid="recovery-undo-prepared-1"]'),
    ).toBeNull();
    expect(
      document.querySelector('[data-testid="recovery-restore-prepared-1"]'),
    ).toBeNull();
  });
  it("labels applied operations as completed rather than unknown", async () => {
    mocks.api.mockResolvedValueOnce({
      ok: true,
      operations: [
        {
          operation_id: "applied-1",
          kind: "delete",
          label: "已执行",
          target_name: "资料册",
          target_count: 1,
          created_at: "",
          status: "applied",
          can_undo: false,
          can_restore: false,
        },
      ],
    });
    mount(LorebookRecoveryDialog, {
      props: { open: true },
      attachTo: document.body,
      global: { plugins: [i18n] },
    });
    await flushPromises();
    expect(document.body.textContent).toContain("已执行");
    expect(document.body.textContent).not.toContain("状态未知");
  });
});
