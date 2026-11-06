const defaults = { theme: 'light', font: 'normal' }
export function preferenceKey(user) {
  return `oto.preferences.${user.id_usuario}`
}
export function readPreferences(storage, user) {
  try {
    const data = JSON.parse(storage?.getItem(preferenceKey(user)) || '{}')
    return {
      theme: ['light', 'dark'].includes(data.theme) ? data.theme : 'light',
      font: ['normal', 'large', 'larger'].includes(data.font) ? data.font : 'normal',
    }
  } catch {
    return { ...defaults }
  }
}
export function savePreferences(storage, user, preferences) {
  storage.setItem(preferenceKey(user), JSON.stringify(preferences))
}
export function applyPreferences(preferences, root = document.documentElement) {
  root.dataset.theme = preferences.theme
  root.style.setProperty(
    '--font-scale',
    { normal: 1, large: 1.14, larger: 1.28 }[preferences.font] || 1,
  )
}
