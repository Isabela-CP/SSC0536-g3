import React from 'react'
import { labelFor } from '../domain/labels.js'
export function Feedback({ kind = 'error', message }) {
  if (!message) return null
  return (
    <div
      className={`feedback feedback-${kind}`}
      role={kind === 'error' ? 'alert' : 'status'}
      tabIndex={-1}
    >
      {message}
    </div>
  )
}
export function FormErrors({ errors = {} }) {
  if (!Object.keys(errors).length) return null
  return (
    <div className="feedback feedback-error" role="alert" tabIndex={-1} data-error-summary>
      <strong>Verifique os campos informados.</strong>
      <ul>
        {Object.entries(errors).map(([path, message]) => (
          <li key={path}>
            {path ? (
              <a
                href={`#field-${path.replaceAll('.', '-')}`}
                onClick={(event) => {
                  event.preventDefault()
                  const field = document.getElementById(`field-${path.replaceAll('.', '-')}`)
                  if (field) {
                    for (let parent = field.parentElement; parent; parent = parent.parentElement)
                      if (parent.tagName === 'DETAILS') parent.open = true
                    field.focus()
                  }
                }}
              >
                {`${labelFor(path)}: ${message}`}
              </a>
            ) : (
              message
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}
