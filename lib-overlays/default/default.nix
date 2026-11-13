final: prev: {
  carton-purifier = {
    readLock = import ./read-lock.nix { lib = final; };
  };
}
