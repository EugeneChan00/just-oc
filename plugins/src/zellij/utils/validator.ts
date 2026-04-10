export interface ValidationResult {
  valid: boolean
  errors: string[]
  sanitized?: string
}

export class Validator {
  static validateSessionName(name: string): ValidationResult {
    const errors: string[] = []
    if (!name || typeof name !== "string") {
      errors.push("Session name is required and must be a string")
    } else {
      if (!/^[a-zA-Z0-9_-]+$/.test(name)) errors.push("Session name can only contain alphanumeric characters, underscores, and hyphens")
      if (name.length > 64) errors.push("Session name must be 64 characters or less")
    }
    return { valid: errors.length === 0, errors, sanitized: name?.trim() }
  }

  static validateCommand(command: string): ValidationResult {
    const errors: string[] = []
    if (!command || typeof command !== "string") {
      errors.push("Command is required and must be a string")
    } else {
      const dangerousPatterns = [/[;&|`$(){}[\]!#]/, /\.\./, /rm\s+-rf/, /sudo/, /curl.*\|.*sh/, /wget.*\|.*sh/]
      for (const pattern of dangerousPatterns) {
        if (pattern.test(command)) errors.push(`Command contains potentially dangerous pattern: ${pattern.source}`)
      }
      if (command.length > 1000) errors.push("Command is too long (max 1000 characters)")
    }
    return { valid: errors.length === 0, errors, sanitized: command?.trim() }
  }

  static validatePluginUrl(url: string): ValidationResult {
    const errors: string[] = []
    if (!url || typeof url !== "string") {
      errors.push("Plugin URL is required and must be a string")
    } else {
      if (!/^(file:|https?:|zellij:)/.test(url)) errors.push("Plugin URL must use file:, http:, https:, or zellij: protocol")
      if (url.startsWith("file:")) {
        if (url.includes("..")) errors.push("Plugin file path cannot contain directory traversal (..)")
        if (!url.match(/file:\/\/(\/tmp\/|\/home\/|\/usr\/share\/|\.\/)/)) errors.push("Plugin file path must be in allowed directories (/tmp, /home, /usr/share, or relative)")
      }
    }
    return { valid: errors.length === 0, errors, sanitized: url?.trim() }
  }

  static validateDirection(direction: string): ValidationResult {
    const errors: string[] = []
    const valid = ["left", "right", "up", "down", "next", "previous"]
    if (!direction || typeof direction !== "string") {
      errors.push("Direction is required and must be a string")
    } else if (!valid.includes(direction.toLowerCase())) {
      errors.push(`Direction must be one of: ${valid.join(", ")}`)
    }
    return { valid: errors.length === 0, errors, sanitized: direction?.toLowerCase() }
  }

  static validateSplitDirection(direction: string): ValidationResult {
    const errors: string[] = []
    const valid = ["right", "down"]
    if (!direction || typeof direction !== "string") {
      errors.push("Split direction is required and must be a string")
    } else if (!valid.includes(direction.toLowerCase())) {
      errors.push(`Split direction must be one of: ${valid.join(", ")}`)
    }
    return { valid: errors.length === 0, errors, sanitized: direction?.toLowerCase() }
  }

  static validateResizeAmount(amount: string): ValidationResult {
    const errors: string[] = []
    const valid = ["increase", "decrease"]
    if (!amount || typeof amount !== "string") {
      errors.push("Resize amount is required and must be a string")
    } else if (!valid.includes(amount.toLowerCase())) {
      errors.push(`Resize amount must be one of: ${valid.join(", ")}`)
    }
    return { valid: errors.length === 0, errors, sanitized: amount?.toLowerCase() }
  }

  static validateText(text: string): ValidationResult {
    const errors: string[] = []
    if (!text || typeof text !== "string") {
      errors.push("Text is required and must be a string")
    } else {
      if (text.length > 10000) errors.push("Text is too long (max 10000 characters)")
      if (/\x1b\[[0-9;]*[mGKH]/.test(text)) errors.push("Text contains ANSI escape sequences which may be dangerous")
    }
    return { valid: errors.length === 0, errors, sanitized: text }
  }

  static validateString(value: string, fieldName: string, maxLength = 256): ValidationResult {
    const errors: string[] = []
    if (!value || typeof value !== "string") {
      errors.push(`${fieldName} is required and must be a string`)
    } else {
      if (value.length > maxLength) errors.push(`${fieldName} is too long (max ${maxLength} characters)`)
      if (value.trim().length === 0) errors.push(`${fieldName} cannot be empty`)
    }
    return { valid: errors.length === 0, errors, sanitized: value?.trim() }
  }

  static validatePath(path: string): ValidationResult {
    const errors: string[] = []
    if (!path || typeof path !== "string") {
      errors.push("Path is required and must be a string")
    } else {
      if (path.includes("..")) errors.push("Path cannot contain directory traversal (..)")
    }
    return { valid: errors.length === 0, errors, sanitized: path?.trim() }
  }

  static validatePaneId(id: string): ValidationResult {
    const errors: string[] = []
    if (!id || typeof id !== "string") {
      errors.push("Pane ID is required and must be a string")
    } else if (!/^(terminal_|plugin_)?\d+$/.test(id)) {
      errors.push("Invalid pane ID format. Expected: 'terminal_1', 'plugin_1', or '1'")
    }
    return { valid: errors.length === 0, errors, sanitized: id?.trim() }
  }
}
