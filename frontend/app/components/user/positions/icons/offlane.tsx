interface IconProps {
  className?: string;
}

export const OfflaneSVG: React.FC<IconProps> = ({ className = "w-4 h-4" }) => {
  return (
    <svg viewBox="0 0 24 24" className={className}>
      <path
        fillRule="evenodd"
        clipRule="evenodd"
        d="M.75 3.3C.75 1.892 1.84.75 3.187.75H20.81c1.347 0 2.441 1.142 2.441 2.55v7.52a8.265 8.265 0 01-.803 3.56C20.953 17.45 17.43 23.25 12 23.25c-5.432 0-8.957-5.8-10.444-8.878a8.259 8.259 0 01-.799-3.553A2510.5 2510.5 0 01.75 3.3zm14.198 2.2a.509.509 0 00-.014-.482.462.462 0 00-.4-.238h-2.48a.469.469 0 00-.41.25c-.558 1.048-2.711 5.076-3.464 6.484-.054.1-.05.223.004.324.058.1.162.162.274.162h2.196c.169 0 .324.094.414.245.086.151.09.338.01.497-.64 1.242-1.93 3.75-2.646 5.148a.16.16 0 00.044.198c.06.046.144.04.198-.018 1.67-1.815 5.673-6.156 7.095-7.697a.338.338 0 00.061-.357.31.31 0 00-.288-.198h-2.008a.477.477 0 01-.407-.24.514.514 0 01-.011-.49c.49-.958 1.343-2.634 1.832-3.588z"
        fill="url(#shield_offlane)"
      ></path>
      <defs>
        <linearGradient
          id="shield_offlane"
          x1="12"
          y1="0.75"
          x2="12"
          y2="23.25"
          gradientUnits="userSpaceOnUse"
        >
          <stop stopColor="hsl(33,79%,46%)"></stop>
          <stop offset="1" stopColor="hsl(34,82%,36%)"></stop>
        </linearGradient>
      </defs>
    </svg>
  );
};
