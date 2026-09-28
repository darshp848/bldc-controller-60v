%% better-md80 FOC current (torque) loop: stability margins and step response
% Discrete PI current loop at 40 kHz (MD80 torque-loop rate) with the real sensing chain:
% 0.5 mOhm shunt, DRV8353 CSA gain 20 V/V, 12-bit ADC on 3.3 V -> 80.6 mA/LSB, and
% 1.5 sample transport delay (computation + PWM update + ADC). Motor: a typical
% MAB/CubeMars 8108-class actuator motor (R and L assumed, see below).
%
% run:  matlab -batch "run('sim/foc_current_loop.m')"   (Control System Toolbox)

clear; close all;
outdir = fullfile(fileparts(mfilename('fullpath')), 'out');
if ~exist(outdir, 'dir'); mkdir(outdir); end

Ts   = 1/40e3;          % control period
Vbus = 48;              % nominal bus
R    = 0.20;            % phase resistance [Ohm]   (assumed, 8108-class)
L    = 90e-6;           % q-axis inductance [H]    (assumed, 8108-class)
lsb  = 3.3/4096/20/0.5e-3;   % A per ADC count
Vmax = Vbus/sqrt(3);    % SVPWM linear limit

s = tf('s');
P = 1/(L*s + R);
D = exp(-1.5*Ts*s);                  % transport delay
res = {};
figure('Position', [100 100 1100 420]);
for bw = [1e3 2.5e3]
    wc = 2*pi*bw;
    Kp = L*wc; Ki = R*wc;            % pole-zero cancellation
    C  = Kp + Ki/s;
    Lo = C*P*D;
    [Gm, Pm, ~, Wcp] = margin(Lo);
    T  = feedback(C*P*D, 1);
    bwc = bandwidth(pade(T, 4))/2/pi;
    res{end+1} = sprintf(['target %.1f kHz: Kp=%.3f V/A, Ki=%.0f V/(A s), phase margin %.1f deg, gain margin ' ...
                          '%.1f dB, crossover %.2f kHz, closed-loop -3 dB %.2f kHz'], ...
                          bw/1e3, Kp, Ki, Pm, 20*log10(Gm), Wcp/2/pi/1e3, bwc/1e3);
    % time domain with saturation, quantisation and discrete control
    N = round(4e-3/Ts); iq = 0; integ = 0; y = zeros(N,1); u = zeros(N,1); ref = zeros(N,1);
    ref(round(0.5e-3/Ts):end) = 20; ref(round(2e-3/Ts):end) = 80;
    ud = [0 0];                                   % 1.5-sample delay (2-sample buffer, 0.5 in plant step)
    Ad = exp(-R/L*Ts); Bd = (1-Ad)/R;
    rng(1);
    for k = 1:N
        meas = lsb*round((iq + 0.05*randn)/lsb);  % 50 mA rms analog noise + quantisation
        e = ref(k) - meas;
        integ = integ + Ki*Ts*e;
        v = Kp*e + integ;
        if abs(v) > Vmax                           % clamp + anti-windup
            v = sign(v)*Vmax; integ = integ - Ki*Ts*e;
        end
        ud = [ud(2) v];
        iq = Ad*iq + Bd*ud(1);
        y(k) = iq; u(k) = v;
    end
    t = (0:N-1)'*Ts*1e3;
    subplot(1,2,find(bw == [1e3 2.5e3]));
    plot(t, ref, 'k--', t, y, 'b'); grid on; xlabel('ms'); ylabel('i_q [A]');
    title(sprintf('%.1f kHz loop, PM %.0f deg', bw/1e3, Pm));
    ripple = std(y(round(1.5e-3/Ts):round(1.95e-3/Ts)));
    res{end} = sprintf('%s, 20 A steady-state noise %.0f mA rms', res{end}, ripple*1e3);
end
saveas(gcf, fullfile(outdir, 'foc_current_loop.png'));
% sampling window: centre-aligned PWM, all low-side FETs on at the counter valley
t_settle = 1.0e-6;                                   % DRV8353 CSA settling to 1 % (datasheet class)
dmax = 1 - 2*t_settle/Ts;
res{end+1} = sprintf('ADC resolution %.1f mA/LSB, +/-%.0f A range; max duty for clean 3-shunt sampling %.1f %%', ...
                     lsb*1e3, 1.65/20/0.5e-3, dmax*100);
fid = fopen(fullfile(outdir, 'foc_current_loop.txt'), 'w');
fprintf(fid, '%s\n', res{:}); fclose(fid);
fprintf('%s\n', res{:});
