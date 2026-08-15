OPENQASM 2.0;
include "qelib1.inc";

qreg q[8];
creg c[8];

// Four nominal component monitors.
h q[0];
rz(1.5707963267948966) q[0];
h q[0];
h q[1];
rz(1.5707963267948966) q[1];
h q[1];
h q[2];
rz(1.5707963267948966) q[2];
h q[2];
h q[3];
rz(1.5707963267948966) q[3];
h q[3];

// Four component monitors with known signed phase offsets.
h q[4];
rz(1.9207963267948966) q[4];
h q[4];
h q[5];
rz(1.2207963267948966) q[5];
h q[5];
h q[6];
rz(2.2207963267948966) q[6];
h q[6];
h q[7];
rz(0.9207963267948966) q[7];
h q[7];

measure q -> c;
