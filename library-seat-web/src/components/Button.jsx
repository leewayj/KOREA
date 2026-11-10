// JavaScript port of the Figma SDS Code Connect Button.
// Source: https://github.com/figma/sds/blob/main/src/ui/primitives/Button/Button.tsx
// Copyright (c) 2024 Figma. MIT license: ./FIGMA-SDS-LICENSE.
import { clsx } from 'clsx'
import React from 'react'
import { Button as RACButton, Link as RACLink } from 'react-aria-components'
import './button.css'

export const Button = React.forwardRef(function Button(
  { className, size = 'medium', variant = 'primary', ...props },
  ref,
) {
  const classNames = clsx(className, 'button', `button-size-${size}`, `button-variant-${variant}`)
  return 'href' in props ? (
    <RACLink {...props} className={classNames} ref={ref}>{props.children}</RACLink>
  ) : (
    <RACButton {...props} className={classNames} ref={ref}>{props.children}</RACButton>
  )
})
