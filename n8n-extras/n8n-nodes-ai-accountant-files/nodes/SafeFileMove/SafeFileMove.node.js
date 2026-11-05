"use strict";

const fs = require("node:fs/promises");
const path = require("node:path");

const DEFAULT_ALLOWED_ROOT = "/home/node/.n8n-files";

function isInsideRoot(candidate, root) {
  const relative = path.relative(root, candidate);
  return relative !== "" && !relative.startsWith("..") && !path.isAbsolute(relative);
}

class SafeFileMove {
  constructor() {
    this.description = {
      displayName: "AI Accountant: Переместить файл",
      name: "aiAccountantSafeFileMove",
      group: ["transform"],
      version: 1,
      description: "Перемещает файл только внутри защищённой папки документов AI Accountant",
      defaults: {
        name: "Переместить файл",
      },
      inputs: ["main"],
      outputs: ["main"],
      properties: [
        {
          displayName: "Исходный путь",
          name: "sourcePath",
          type: "string",
          default: "",
          required: true,
          placeholder: "/home/node/.n8n-files/Организация/Входящие документы/файл.pdf",
        },
        {
          displayName: "Целевой путь",
          name: "destinationPath",
          type: "string",
          default: "",
          required: true,
          placeholder: "/home/node/.n8n-files/Организация/Задача поставлена/файл.pdf",
        },
      ],
    };
  }

  async execute() {
    const items = this.getInputData();
    const output = [];
    const allowedRoot = path.resolve(process.env.AI_ACCOUNTANT_FILES_ROOT || DEFAULT_ALLOWED_ROOT);

    for (let index = 0; index < items.length; index += 1) {
      const sourcePath = path.resolve(this.getNodeParameter("sourcePath", index));
      const destinationPath = path.resolve(this.getNodeParameter("destinationPath", index));
      const result = {
        success: false,
        source_path: sourcePath,
        destination_path: destinationPath,
      };

      try {
        if (!isInsideRoot(sourcePath, allowedRoot) || !isInsideRoot(destinationPath, allowedRoot)) {
          throw new Error(`Разрешены только пути внутри ${allowedRoot}`);
        }

        const source = await fs.stat(sourcePath);
        if (!source.isFile()) {
          throw new Error("Исходный путь не является файлом");
        }

        const destinationDirectory = path.dirname(destinationPath);
        const destinationDirectoryStat = await fs.stat(destinationDirectory);
        if (!destinationDirectoryStat.isDirectory()) {
          throw new Error("Целевая папка не существует");
        }

        try {
          await fs.access(destinationPath);
          throw new Error("Целевой файл уже существует; перезапись запрещена");
        } catch (error) {
          if (error && error.code !== "ENOENT") {
            throw error;
          }
        }

        await fs.rename(sourcePath, destinationPath);
        result.success = true;
      } catch (error) {
        result.error = error instanceof Error ? error.message : String(error);
      }

      output.push({
        json: {
          ...items[index].json,
          file_move: result,
        },
        pairedItem: { item: index },
      });
    }

    return [output];
  }
}

module.exports = { SafeFileMove };
