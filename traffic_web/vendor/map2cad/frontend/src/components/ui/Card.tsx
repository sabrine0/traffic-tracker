interface CardProps {
  title?: string;
  children: React.ReactNode;
  className?: string;
}

export default function Card({ title, children, className = "" }: CardProps) {
  return (
    <div className={`rounded-lg border border-gray-200 bg-white p-4 shadow-sm ${className}`}>
      {title && <h3 className="mb-2 text-sm font-semibold text-gray-700">{title}</h3>}
      {children}
    </div>
  );
}
