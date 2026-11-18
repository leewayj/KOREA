import { useId } from "react";
export default function InputField({ label, ...props }) {
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input id={id} required {...props} />
    </div>
  );
}
