import { Image } from "django-prose-editor/editor";

const fallbackPromptAttrs = (editor) => {
  const current = editor.getAttributes("ImageDialog");
  const src = window.prompt("Image URL", current.src || "");
  if (!src) {
    return null;
  }
  const attrs = {
    src,
    alt: window.prompt("Alt text", current.alt || "") || "",
    width: window.prompt("Width", current.width || "") || "",
    height: window.prompt("Height", current.height || "") || "",
    border: window.prompt("Border", current.border || "") || "",
    hspace: window.prompt("HSpace", current.hspace || "") || "",
    vspace: window.prompt("VSpace", current.vspace || "") || "",
    align: window.prompt("Alignment (left/right/center)", current.align || "") || "",
  };
  return Object.fromEntries(
    Object.entries(attrs).filter(([, value]) => value !== "")
  );
};

const openImageDialog = (editor) => {
  if (typeof HTMLDialogElement === "undefined") {
    return fallbackPromptAttrs(editor);
  }

  const current = editor.getAttributes("ImageDialog");
  const dialog = document.createElement("dialog");
  dialog.style.padding = "0";
  dialog.style.border = "1px solid var(--border-color, #d1d5db)";
  dialog.style.borderRadius = "8px";
  dialog.style.width = "min(720px, 92vw)";

  dialog.innerHTML = `
    <form method="dialog" style="padding:16px; display:grid; gap:12px;">
      <div style="font-weight:600; font-size:16px;">Image Properties</div>
      <label style="display:grid; gap:4px;">
        URL*
        <input name="src" required style="width:100%;" />
      </label>
      <label style="display:grid; gap:4px;">
        Alternative Text
        <input name="alt" style="width:100%;" />
      </label>
      <div style="display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px;">
        <label style="display:grid; gap:4px;">
          Width
          <input name="width" />
        </label>
        <label style="display:grid; gap:4px;">
          Height
          <input name="height" />
        </label>
        <label style="display:grid; gap:4px;">
          Border
          <input name="border" />
        </label>
        <label style="display:grid; gap:4px;">
          HSpace
          <input name="hspace" />
        </label>
        <label style="display:grid; gap:4px;">
          VSpace
          <input name="vspace" />
        </label>
        <label style="display:grid; gap:4px;">
          Alignment
          <input name="align" placeholder="left/right/center" />
        </label>
      </div>
      <label style="display:grid; gap:4px;">
        Preview
        <div style="border:1px solid var(--border-color, #d1d5db); padding:8px; min-height:120px;">
          <img data-preview style="max-width:100%; height:auto;" />
        </div>
      </label>
      <menu style="display:flex; justify-content:flex-end; gap:8px; padding:0;">
        <button type="button" data-action="cancel">Cancel</button>
        <button value="ok">OK</button>
      </menu>
    </form>
  `;

  const form = dialog.querySelector("form");
  const preview = dialog.querySelector("[data-preview]");
  const setValue = (name, value) => {
    const field = form.elements[name];
    if (field) {
      field.value = value || "";
    }
  };

  setValue("src", current.src);
  setValue("alt", current.alt);
  setValue("width", current.width);
  setValue("height", current.height);
  setValue("border", current.border);
  setValue("hspace", current.hspace);
  setValue("vspace", current.vspace);
  setValue("align", current.align);

  const normalizeDimension = (value) => {
    if (!value) {
      return "";
    }
    const trimmed = value.trim();
    if (/^\d+$/.test(trimmed)) {
      return `${trimmed}px`;
    }
    return trimmed;
  };

  const parseCombinedDimensions = (value) => {
    if (!value) {
      return null;
    }
    const match = value.match(/^(\d+)\s*[xX]\s*(\d+)$/);
    if (!match) {
      return null;
    }
    return { width: match[1], height: match[2] };
  };

  const updatePreview = () => {
    const widthValue = form.elements.width.value;
    const heightValue = form.elements.height.value;
    const combined =
      parseCombinedDimensions(widthValue) || parseCombinedDimensions(heightValue);

    if (combined) {
      form.elements.width.value = combined.width;
      form.elements.height.value = combined.height;
    }

    preview.src = form.elements.src.value || "";
    preview.alt = form.elements.alt.value || "";
    preview.style.width = normalizeDimension(form.elements.width.value);
    preview.style.height = normalizeDimension(form.elements.height.value);
    preview.style.border = form.elements.border.value
      ? `${form.elements.border.value}px solid currentColor`
      : "";
  };

  form.elements.src.addEventListener("input", updatePreview);
  form.elements.alt.addEventListener("input", updatePreview);
  form.elements.width.addEventListener("input", updatePreview);
  form.elements.height.addEventListener("input", updatePreview);
  form.elements.border.addEventListener("input", updatePreview);
  updatePreview();

  document.body.appendChild(dialog);
  dialog.showModal();

  return new Promise((resolve) => {
    dialog.querySelector("[data-action='cancel']").addEventListener("click", () => {
      dialog.close("cancel");
    });
    dialog.addEventListener(
      "close",
      () => {
        if (dialog.returnValue !== "ok") {
          dialog.remove();
          resolve(null);
          return;
        }
        const attrs = {
          src: form.elements.src.value,
          alt: form.elements.alt.value,
          width: form.elements.width.value,
          height: form.elements.height.value,
          border: form.elements.border.value,
          hspace: form.elements.hspace.value,
          vspace: form.elements.vspace.value,
          align: form.elements.align.value,
        };
        dialog.remove();
        resolve(
          Object.fromEntries(
            Object.entries(attrs).filter(([, value]) => value !== "")
          )
        );
      },
      { once: true }
    );
  });
};

export const ImageDialog = Image.extend({
  name: "ImageDialog",

  addAttributes() {
    return {
      ...this.parent?.(),
      width: { default: null },
      height: { default: null },
      border: { default: null },
      hspace: { default: null },
      vspace: { default: null },
      align: { default: null },
    };
  },

  addMenuItems({ buttons, menu }) {
    menu.defineItem({
      name: "imageDialog",
      groups: "nodes",
      button: buttons.material("image", "Insert image"),
      enabled: () => true,
      active: (editor) => editor.isActive("ImageDialog"),
      command: (editor) => {
        const result = openImageDialog(editor);
        if (result instanceof Promise) {
          result.then((attrs) => {
            if (!attrs) {
              return;
            }
            editor.chain().focus().setImage(attrs).run();
          });
          return true;
        }
        if (!result) {
          return false;
        }
        return editor.chain().focus().setImage(result).run();
      },
    });
  },
});
