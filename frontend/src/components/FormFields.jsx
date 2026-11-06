import React from 'react'
import { resolveSchema, schemas, REQUIRED } from '../domain/establishment.js'
import { labelFor } from '../domain/labels.js'

const payments = ['PIX', 'CREDITO', 'DEBITO', 'DINHEIRO', 'BOLETO', 'TRANSFERENCIA']
export function Field({ path, schema: raw, value, onChange, error, disabled = false, required = false, compact = false, options }) {
  const schema = resolveSchema(raw)
  const label = labelFor(path)
  const id = `field-${path.replaceAll('.', '-')}`
  const common = { id, name: path, disabled, 'aria-invalid': !!error, 'aria-describedby': error ? `${id}-error` : undefined, 'aria-required': required }
  const update = next => onChange(path, next)
  let input
  if (schema.type === 'boolean') {
    input = <div className="checkbox-line"><label htmlFor={id}><input {...common} type="checkbox" checked={value === true} onChange={event => update(event.target.checked)} />{label}</label>{schema.nullable && value != null && !disabled && <button type="button" className="clear-value" title={`Limpar ${label}`} aria-label={`Limpar ${label}`} onClick={() => update(null)}>×</button>}</div>
  } else if (path.endsWith('formas_pagamento')) {
    const selected = Array.isArray(value) ? value : []
    input = <fieldset className="payments" disabled={disabled}><legend>{label}</legend>{payments.map(code => <label key={code}><input type="checkbox" checked={selected.includes(code)} onChange={event => update(event.target.checked ? [...selected, code] : selected.filter(entry => entry !== code))} />{({ CREDITO: 'Crédito', DEBITO: 'Débito', DINHEIRO: 'Dinheiro', BOLETO: 'Boleto', TRANSFERENCIA: 'Transferência' })[code] || code}</label>)}<label className="other-payments">Outras formas<textarea aria-label="Outras formas de pagamento" rows={2} value={selected.filter(entry => !payments.includes(entry)).join('\n')} onChange={event => update([...selected.filter(entry => payments.includes(entry)), ...event.target.value.split('\n').filter(Boolean)])} /></label></fieldset>
  } else if (schema.enum || options) {
    input = <select {...common} value={value ?? ''} onChange={event => update(event.target.value || (schema.nullable ? null : ''))}><option value="">{compact ? label : 'Selecione'}</option>{(options || schema.enum.filter(entry => entry != null).map(entry => ({ value: entry, label: labelFor(String(entry)) }))).map(option => <option value={option.value} key={option.value}>{option.label}</option>)}</select>
  } else if (schema.type === 'array' || ['observacoes', 'regras_reserva', 'horario_funcionamento_descritivo'].includes(path.split('.').at(-1))) {
    input = <textarea {...common} rows={3} placeholder={schema.type === 'array' ? 'Um valor por linha' : label} value={Array.isArray(value) ? value.join('\n') : value ?? ''} onChange={event => update(event.target.value)} />
  } else {
    const type = schema.format === 'date' ? 'date' : schema.format === 'time' ? 'time' : schema.format === 'email' ? 'email' : ['integer', 'number'].includes(schema.type) ? 'number' : 'text'
    input = <input {...common} type={type} placeholder={label} value={value ?? ''} min={schema.minimum} max={schema.maximum} minLength={schema.minLength} maxLength={schema.maxLength} step={schema.type === 'integer' ? '1' : type === 'number' ? 'any' : type === 'time' ? '1' : undefined} onChange={event => update(event.target.value)} />
  }
  const wide = ['nome_fantasia', 'razao_social', 'endereco'].includes(path) || schema.type === 'array' || path.endsWith('observacoes')
  return <div className={`form-field ${wide ? 'span-two' : ''} ${schema.type === 'boolean' ? 'boolean-field' : ''}`}>
    {schema.type !== 'boolean' && !path.endsWith('formas_pagamento') && <label className={compact ? 'sr-only' : 'field-label'} htmlFor={id}>{label}{required && <span aria-hidden="true"> *</span>}</label>}
    {input}
    {error && <span className="field-error" id={`${id}-error`}>{error}</span>}
  </div>
}

export function SchemaFields({ schema: raw, prefix = '', draft, errors = {}, onChange, disabled = false }) {
  const schema = resolveSchema(raw)
  return <div className="field-grid">{Object.entries(schema.properties || {}).map(([key, rawField]) => {
    const path = prefix ? `${prefix}.${key}` : key
    const field = resolveSchema(rawField)
    if (field.type === 'object') return <details className="subgroup span-two" key={path}><summary>{labelFor(path)}</summary><SchemaFields schema={field} prefix={path} draft={draft} errors={errors} onChange={onChange} disabled={disabled} /></details>
    return <Field key={path} path={path} schema={field} value={draft[path]} onChange={onChange} error={errors[path]} disabled={disabled} />
  })}</div>
}

export function RootFields({ fields, draft, errors = {}, onChange, disabled = false, protectedDisabled = false, compact = false, categories = [], mode = 'edit' }) {
  return <div className="field-grid">{fields.map(path => <Field key={path} path={path} schema={schemas.EstabelecimentoCreate.properties[path]} value={draft[path]} onChange={onChange} error={errors[path]} compact={compact} disabled={disabled || (protectedDisabled && ['cnpj', 'razao_social'].includes(path))} required={mode === 'create' && REQUIRED.includes(path)} options={path === 'id_categoria' ? categories.map(item => ({ value: item.id_categoria, label: item.nome_categoria })) : undefined} />)}</div>
}
