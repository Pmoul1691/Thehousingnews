import React from "react";

export default function Declined() {
  return (
    <div className="container-prose py-24 text-center animate-fade-up">
      <p className="uppercase-label mb-3">Membership decision</p>
      <h1 className="font-display font-semibold text-3xl sm:text-4xl ink mb-6">Not this time.</h1>
      <p className="font-serif text-lg leading-relaxed text-[#2C2410]/80 max-w-prose mx-auto">
        Thanks for asking to join. I am not approving membership right now. The room is small on purpose.
      </p>
      <p className="font-serif text-base mt-6 text-muted-ink">You can try again in six months.</p>
    </div>
  );
}
