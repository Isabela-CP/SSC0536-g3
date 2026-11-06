import React, { useEffect, useRef } from 'react'
export default function Modal({ title, onClose, busy = false, children }) {
  const ref = useRef(null)
  useEffect(() => {
    const previous = document.activeElement
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    ref.current?.querySelector('textarea,input,button')?.focus()
    return () => { document.body.style.overflow = overflow; previous?.focus() }
  }, [])
  function keys(event) {
    if (event.key === 'Escape' && !busy) { event.preventDefault(); onClose() }
    if (event.key !== 'Tab') return
    const fields = [...ref.current.querySelectorAll('button:not(:disabled),textarea:not(:disabled),input:not(:disabled),a[href]')]
    if (!fields.length) { event.preventDefault(); return }
    if (event.shiftKey && document.activeElement === fields[0]) { event.preventDefault(); fields.at(-1).focus() }
    else if (!event.shiftKey && document.activeElement === fields.at(-1)) { event.preventDefault(); fields[0].focus() }
  }
  return <div className="modal-backdrop" onMouseDown={event => { if (event.target === event.currentTarget && !busy) onClose() }}><section className="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title" aria-busy={busy} ref={ref} onKeyDown={keys}><h2 id="modal-title">{title}</h2>{children}</section></div>
}
