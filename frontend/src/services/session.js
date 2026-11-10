export function createSession(storage, now = () => Date.now()) {
  const clear = () => {
    storage?.removeItem('oto.accessToken')
    storage?.removeItem('oto.expiresAt')
  }
  return {
    clear,
    token() {
      const token = storage?.getItem('oto.accessToken')
      const expiration = Number(storage?.getItem('oto.expiresAt'))
      if (token && (!Number.isFinite(expiration) || expiration <= now())) {
        clear()
        return null
      }
      return token || null
    },
    save(result) {
      if (!result.access_token || !Number.isFinite(result.expires_in) || result.expires_in <= 0)
        throw new Error('Resposta de sessão inválida.')
      try {
        storage.setItem('oto.accessToken', result.access_token)
        storage.setItem('oto.expiresAt', String(now() + result.expires_in * 1000))
      } catch (error) {
        clear()
        throw new Error('Não foi possível manter a sessão neste navegador.', { cause: error })
      }
    },
  }
}
