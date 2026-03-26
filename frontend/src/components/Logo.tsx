import logo from '/logo.jpeg'

interface LogoProps {
  size?: number
  className?: string
}

export function Logo({ size = 32, className }: LogoProps) {
  return (
    <img
      src={logo}
      alt="Peaky Peek"
      width={size}
      height={size}
      className={className}
      style={{ borderRadius: 6, objectFit: 'contain' }}
    />
  )
}
