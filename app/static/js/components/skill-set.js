import { escapeHtml } from "../core/html.js"

export function createSkillSetEditor({ dom, state, onChange = () => {} }) {
  let initialized = false

  function emitChange() {
    onChange(state.readSelectedSkills())
  }

  function renderSelectedSkillSet() {
    const selectedSkills = state.readSelectedSkills()
    dom.selectedSkillCount.textContent = `${selectedSkills.length} 个技能`

    if (!selectedSkills.length) {
      dom.selectedSkillsOutput.innerHTML = `<p class="muted">当前没有手动指定 skill，将按意图自动推荐。</p>`
      return
    }

    dom.selectedSkillsOutput.innerHTML = selectedSkills
      .map((skillName, index) => {
        const descriptor = state.findSkillDescriptor(skillName)
        const title = descriptor && descriptor.title ? descriptor.title : skillName
        const sourceLabel = descriptor ? "已注册" : "自定义"
        const variantClass = descriptor ? "registered" : "custom"

        return `
          <article class="skill-pill ${variantClass}">
            <span class="skill-pill-order">${index + 1}</span>
            <div class="skill-pill-copy">
              <strong>${escapeHtml(title)}</strong>
              <span>${escapeHtml(skillName)} · ${escapeHtml(sourceLabel)}</span>
            </div>
            <button type="button" class="skill-pill-remove" data-skill-remove="${escapeHtml(skillName)}">移除</button>
          </article>
        `
      })
      .join("")
  }

  function renderSkillPicker(message = "") {
    const availableSkills = state.data.availableSkills || []

    if (message) {
      dom.skillPickerOutput.innerHTML = `<p class="muted">${escapeHtml(message)}</p>`
      return
    }

    if (!availableSkills.length) {
      dom.skillPickerOutput.innerHTML = `<p class="muted">当前没有可选择的已注册 skill。</p>`
      return
    }

    dom.skillPickerOutput.innerHTML = availableSkills
      .map((skill) => {
        const selected = state.data.selectedSkills.includes(skill.name)
        const tags = Array.isArray(skill.tags) && skill.tags.length
          ? skill.tags.map((tag) => `<span class="skill-meta-pill">${escapeHtml(tag)}</span>`).join("")
          : `<span class="skill-meta-pill">未分类</span>`

        return `
          <article class="skill-picker-card ${selected ? "active" : ""}">
            <div class="skill-picker-head">
              <div class="skill-picker-copy">
                <strong>${escapeHtml(skill.title)}</strong>
                <p>${escapeHtml(skill.description)}</p>
              </div>
              <button
                type="button"
                class="skill-picker-button ${selected ? "active" : ""}"
                data-skill-toggle="${escapeHtml(skill.name)}"
              >
                ${selected ? "移出" : "加入"}
              </button>
            </div>
            <div class="skill-picker-meta">
              <span class="skill-meta-pill">标识：${escapeHtml(skill.name)}</span>
              ${tags}
            </div>
          </article>
        `
      })
      .join("")
  }

  function render({ message = "" } = {}) {
    renderSelectedSkillSet()
    renderSkillPicker(message)
  }

  function setCatalog(skills) {
    state.setAvailableSkills(skills)
    render()
  }

  function setCatalogError(message) {
    state.setAvailableSkills([])
    render({ message })
  }

  function setSelection(skillNames, { notify = true } = {}) {
    state.setSelectedSkills(skillNames)
    render()
    if (notify) {
      emitChange()
    }
  }

  function addCustomSkillFromInput() {
    const skillName = dom.customSkillNameInput.value.trim()
    if (!skillName) {
      dom.customSkillNameInput.setCustomValidity("请输入要加入 Skill Set 的 skill 名称。")
      dom.customSkillNameInput.reportValidity()
      return
    }

    dom.customSkillNameInput.setCustomValidity("")

    if (state.addSelectedSkill(skillName)) {
      dom.customSkillNameInput.value = ""
      render()
      emitChange()
    }
  }

  function handleSelectedSkillClick(event) {
    const button = event.target.closest("[data-skill-remove]")
    if (!button) {
      return
    }

    if (state.removeSelectedSkill(button.dataset.skillRemove)) {
      render()
      emitChange()
    }
  }

  function handleSkillPickerClick(event) {
    const button = event.target.closest("[data-skill-toggle]")
    if (!button) {
      return
    }

    const skillName = button.dataset.skillToggle
    if (!skillName) {
      return
    }

    if (state.data.selectedSkills.includes(skillName)) {
      state.removeSelectedSkill(skillName)
    } else {
      state.addSelectedSkill(skillName)
    }

    render()
    emitChange()
  }

  function init() {
    if (initialized) {
      render()
      return
    }

    dom.selectedSkillsOutput.addEventListener("click", handleSelectedSkillClick)
    dom.skillPickerOutput.addEventListener("click", handleSkillPickerClick)
    dom.addCustomSkillButton.addEventListener("click", addCustomSkillFromInput)
    dom.customSkillNameInput.addEventListener("input", () => {
      dom.customSkillNameInput.setCustomValidity("")
    })
    dom.customSkillNameInput.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") {
        return
      }
      event.preventDefault()
      addCustomSkillFromInput()
    })

    initialized = true
    render()
  }

  return {
    init,
    render,
    setCatalog,
    setCatalogError,
    setSelection,
    readSelection: () => state.readSelectedSkills(),
  }
}
