interface LogoProps {
  size?: number;
}

export default function Logo({ size = 34 }: LogoProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 44 44">
      <rect width="44" height="44" rx="11" fill="#E2EAEE" />
      <path
        d="M10 22 L10 33 L34 33 L34 18 L22 9 L10 18"
        stroke="#2F5770"
        strokeWidth={2.2}
        fill="none"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle
        cx="31"
        cy="31"
        r="7.5"
        fill="#E2EAEE"
        stroke="#2F5770"
        strokeWidth={1.4}
      />
      <path
        d="M28 31 L30.2 33.3 L34 28.5"
        stroke="#2F5770"
        strokeWidth={1.7}
        fill="none"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
