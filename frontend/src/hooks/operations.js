import { useEffect, useRef, useState } from 'react'
import { operationError } from '../domain/operations.js'
export function useOperation() {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(null),
    [message, setMessage] = useState('')
  const pending = useRef(false),
    mounted = useRef(true)
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])
  return {
    busy,
    error,
    message,
    clear() {
      setError(null)
      setMessage('')
    },
    success: setMessage,
    async run(action, done, failed) {
      if (pending.current) return
      pending.current = true
      setBusy(true)
      setError(null)
      setMessage('')
      try {
        const result = await action()
        if (mounted.current) done?.(result)
      } catch (error) {
        if (mounted.current) {
          failed?.(error)
          setError(operationError(error))
        }
      } finally {
        pending.current = false
        if (mounted.current) setBusy(false)
      }
    },
  }
}
export function useResource(loader, dependencies, initialData = null) {
  const [state, setState] = useState({
      loading: initialData === null,
      data: initialData,
      error: null,
    }),
    [version, setVersion] = useState(0)
  useEffect(() => {
    let active = true
    const controller = new AbortController()
    setState((previous) => ({ ...previous, loading: true, error: null }))
    Promise.resolve()
      .then(() => loader({ signal: controller.signal }))
      .then((data) => {
        if (active) setState({ loading: false, data, error: null })
      })
      .catch((error) => {
        if (active && error.name !== 'AbortError')
          setState((previous) => ({
            ...previous,
            loading: false,
            error: operationError(error).message,
          }))
      })
    return () => {
      active = false
      controller.abort()
    }
  }, [...dependencies, version])
  return { ...state, reload: () => setVersion((value) => value + 1) }
}
