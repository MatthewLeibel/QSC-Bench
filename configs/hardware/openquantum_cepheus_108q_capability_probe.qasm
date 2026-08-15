OPENQASM 2.0;
include "qelib1.inc";

qreg q[108];
creg c[108];

// Diagnostic only: exercise and measure every advertised qubit without CZ gates.
h q;
rz(1.5707963267948966) q;
h q;
measure q -> c;
