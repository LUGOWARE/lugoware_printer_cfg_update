"""PC factory QC only. Never starts automatically; screen diagnostics stay unchanged."""
import math
import re
import statistics


def route(source, parking=False):
    # Accept only the simple manual DOCK_n/PARK_n layout, not print macros.
    if parking:
        if 'FROM_PRIME' not in source or source.count('{% else %}') != 1:
            raise ValueError('Unsupported parking macro layout')
        source=source.split('{% else %}',1)[1]
    moves=[]
    for line in source.splitlines():
        line=line.split(';',1)[0].split('#',1)[0].strip()
        if not re.match(r'^G[01]\s',line,re.I):continue
        if '{' in line or '}' in line:raise ValueError('Dynamic docking coordinates unsupported')
        fields={k.upper():float(v) for k,v in re.findall(r'([XYZEF])\s*(-?\d+(?:\.\d+)?)',line,re.I)}
        if 'Z' in fields:
            if 'X' in fields or 'Y' in fields:raise ValueError('Mixed docking Z movement unsupported')
            continue
        if 'X' not in fields and 'Y' not in fields:continue
        if 'F' not in fields or fields['F']<=0:raise ValueError('Docking speed missing')
        moves.append(([fields.get('X'),fields.get('Y'),None],fields['F']/60.))
    if len(moves)<5:raise ValueError('Docking route unavailable')
    return moves


class FactoryQC:
    def __init__(self, host):
        self.h=host;self.armed=False

    def begin(self,minutes,token):
        if minutes not in (5,30,60):raise ValueError('Select 5, 30 or 60 minutes')
        if not re.fullmatch('[a-f0-9]{32}',token):raise ValueError('Invalid QC session')
        h=self.h
        h.validate('motor')
        if h.status('extruder').get('temperature',999)>=50:
            raise ValueError('Wait until nozzle is below 50C')
        cfg=h.status('configfile')['settings']
        if cfg['extruder']['max_temp']<=250 or cfg['heater_bed']['max_temp']<=60:
            raise ValueError('QC temperatures exceed heater configuration')
        bounds=h.status('toolhead')
        self.routes=[]
        for n in range(4):
            pair=[route(cfg['gcode_macro dock_'+str(n)]['gcode']),
                  route(cfg['gcode_macro park_'+str(n)]['gcode'],True)]
            for path in pair:
                for xyz,speed in path:
                    for axis in (0,1):
                        if xyz[axis] is not None and not bounds['axis_minimum'][axis]<=xyz[axis]<=bounds['axis_maximum'][axis]:
                            raise ValueError('Docking route exceeds axis limits')
            self.routes.append(pair)
        self.motor_moves=self.motor_plan()
        self.token=token;self.minutes=minutes;self.duration=minutes*60
        self.contact=h.reactor.monotonic();self.current_tool=None;self.phase='home'
        self.rounds=0;self.tool=0;self.motor_cycles=0;self.probe_sets=0;self.deploys=0;self.samples=[]
        self.saved_limits=(bounds['max_velocity'],bounds['max_accel'])
        h.start('factory');self.armed=True
        h.data={'schema':1,'minutes':minutes,'docking_rounds':0,'motor_cycles':0,'probe_sets':0,'deployment_cycles':0,
                'nozzle_target':250,'bed_target':60,'extrusion':False}
        h.data['factory_qc']=True

    def heartbeat(self,token):
        if token!=self.token:raise ValueError('QC session does not match')
        self.contact=self.h.reactor.monotonic()

    def detached(self):
        if self.h.status('filament_switch_sensor toolhead_sensor').get('filament_detected',True):
            raise ValueError('Tool still detected after parking; inspect the head')

    def interrupted(self):
        h=self.h
        if h.reactor.monotonic()-self.contact>45:
            raise ValueError('PC connection lost; QC stopped')
        if h.reactor.monotonic()-h.started>self.duration+600:
            raise ValueError('Factory QC safety time limit reached')
        if h.printing():raise ValueError('Print activity detected')
        return h.stop_requested

    def path(self,steps,allow_stop=True):
        h=self.h
        for xyz,speed in steps:
            if not h.active:return False
            if allow_stop and self.interrupted():return False
            h.toolhead.manual_move(list(xyz),speed)
            h.reactor.pause(h.reactor.NOW)
        h.toolhead.wait_moves()
        return True

    def park(self):
        if self.current_tool is not None:
            n=self.current_tool
            self.h.phase='factory_parking'
            self.h.script('SET_VELOCITY_LIMIT VELOCITY=500 ACCEL=10000')
            self.path(self.routes[n][1],allow_stop=False)
            self.detached();self.current_tool=None

    def tick(self,now):
        h=self.h
        if self.interrupted():
            self.park();h.finish('stopped','Factory QC stopped');return
        h.data.update(activity=self.phase,temperature=h.status('extruder').get('temperature'),bed_temperature=h.status('heater_bed').get('temperature'))
        if self.phase=='home':
            h.phase='factory_homing';h.script('G28')
            if set(h.status('toolhead').get('homed_axes',''))!=set('xyz'):raise ValueError('XYZ home incomplete')
            h.script('Probe_Stow')
            h.toolhead.manual_move([None,None,20.],min(40.,h.toolhead.get_kinematics().max_z_velocity))
            h.toolhead.wait_moves()
            h.script('SET_MULTI_PIN_MODE PIN=dual_hotend_heater MODE=0\nM104 S250\nM140 S60\nM106 S255\nSET_FAN_SPEED FAN=chamber_fan SPEED=1')
            self.stage_start=h.reactor.monotonic();self.test_start=self.stage_start;self.phase='docking';return
        if self.phase=='docking':
            self.detached();h.script('SET_VELOCITY_LIMIT VELOCITY=500 ACCEL=10000')
            self.current_tool=self.tool;h.phase='factory_docking';h.data['tool']=self.tool+1
            self.path(self.routes[self.tool][0],allow_stop=False);self.park()
            if h.stop_requested:h.finish('stopped','Factory QC stopped');return
            self.tool+=1
            if self.tool==4:
                self.tool=0;self.rounds+=1;h.data['docking_rounds']=self.rounds
                if (self.minutes == 5 and self.rounds >= 3) or (self.minutes != 5 and self.rounds >= 5 and h.reactor.monotonic()-self.test_start >= self.duration*.30):
                    self.phase='motor';self.stage_start=h.reactor.monotonic()
            return
        if self.phase=='motor':
            self.detached();h.phase='factory_motor'
            h.script('Probe_Stow\nSET_VELOCITY_LIMIT VELOCITY=500 ACCEL=16000')
            if not self.path([(xyz,speed) for xyz,speed,*_ in self.motor_moves]):
                h.toolhead.wait_moves();h.finish('stopped','Factory QC stopped');return
            self.motor_cycles+=1;h.data['motor_cycles']=self.motor_cycles
            if h.reactor.monotonic()-self.test_start>=self.duration*.80:
                self.phase='probe';self.stage_start=h.reactor.monotonic()
                x,y,z=h.geometry();self.probe_z=z
                h.move([None,None,z],min(40.,h.toolhead.get_kinematics().max_z_velocity));h.move([x,y,None],100.)
            return
        if self.phase=='probe':
            self.detached();h.phase='factory_probe'
            wrapper=h.printer.lookup_object('probe').mcu_probe
            if self.deploys<10:
                h.script('Probe_Stow');h.toolhead.dwell(.05);h.script('Probe_Deploy');h.toolhead.dwell(.2);h.toolhead.wait_moves()
                if wrapper.query_endstop(h.toolhead.get_last_move_time()):raise ValueError('Probe remained triggered after deployment')
                h.script('Probe_Stow');self.deploys+=1;h.data['deployment_cycles']=self.deploys;return
            h.script('PROBE SAMPLES=3')
            values=h.status('probe_auto_recovery').get('last_samples',[])
            if len(values)!=3 or not all(math.isfinite(v) for v in values):raise ValueError('Probe samples unavailable')
            self.samples.extend(values);self.samples=self.samples[-300:]
            self.probe_sets+=1;h.data['probe_sets']=self.probe_sets
            h.data['probe_spread']=max(self.samples)-min(self.samples)
            h.data['probe_mean']=statistics.mean(self.samples)
            h.move([None,None,self.probe_z],min(40.,h.toolhead.get_kinematics().max_z_velocity));h.script('Probe_Stow')
            if self.probe_sets>=10 and h.reactor.monotonic()-self.test_start>=self.duration:
                h.finish('review','Factory QC complete; operator checklist required')

    def cleanup(self):
        if not self.armed:return
        h=self.h
        for command in ('TURN_OFF_HEATERS','M107','SET_FAN_SPEED FAN=chamber_fan SPEED=0','Probe_Stow',
                        'SET_MULTI_PIN_MODE PIN=dual_hotend_heater MODE=0',
                        'SET_VELOCITY_LIMIT VELOCITY=%s ACCEL=%s'%self.saved_limits):
            try:h.script(command)
            except Exception:h.data.setdefault('cleanup_errors',[]).append(command)
        if self.current_tool is not None:h.data['manual_parking_required']=True
        self.armed=False

    def motor_geometry(self):return self.h.motor_geometry()

    @property
    def model(self):return self.h.model

    @property
    def z_speed(self):return min(40.,self.h.toolhead.get_kinematics().max_z_velocity)

    def motor_plan(self):
        x,y,z = self.motor_geometry()
        left,right,bottom,top = 1.,x,0.,229.
        cx,cy = (left+right)/2.,(bottom+top)/2.
        plan = [([None,None,20.],self.z_speed,'position',0)]
        def move(px,py,activity='position',cycle=0,speed=100.):
            plan.append(([px,py,20.],speed,activity,cycle))
        for start,end,activity in (
                ((left,cy),(right,cy),'x'), ((cx,bottom),(cx,top),'y'),
                ((left,bottom),(right,top),'diagonal_a'),
                ((left,top),(right,bottom),'diagonal_b')):
            move(*start)
            for cycle in range(1,6):
                move(*end,activity,cycle,500.)
                move(*start,activity,cycle,500.)
        # Ellipse inset 1 mm from the model's nominal XY envelope.
        ecx,ecy=x/2.,y/2.
        rx,ry=x/2.-1.,y/2.-1.
        move(ecx+rx,ecy)
        # <= 0.05 mm chord error, avoiding thousands of tiny segments.
        segments=math.ceil(math.pi/math.acos(1.-.05/max(rx,ry)))
        for cycle in range(1,6):
            for i in range(1,segments+1):
                angle=2.*math.pi*i/segments
                move(ecx+rx*math.cos(angle),ecy+ry*math.sin(angle),'ellipse',cycle,500.)
        # Small, expanding diagonal zigzags at each corner (0.4 .. 20 mm).
        for corner,(flipx,flipy) in enumerate(((False,False),(True,False),(True,True),(False,True)),1):
            def corner_point(dx,dy):
                return (right-dx if flipx else left+dx,
                        top-dy if flipy else bottom+dy)
            move(*corner_point(0.,0.))
            for cycle in range(1,51):
                width=.4*cycle
                move(*corner_point(width,0.),'infill_'+str(corner),cycle,500.)
                move(*corner_point(0.,width),'infill_'+str(corner),cycle,500.)
        move(cx,cy)
        heights = ([0.,52.5,105.,157.5,210.,260.] if self.model == 'M'
                   else [0.,60.,120.,180.,240.,300.,360.])
        for height in heights:
            plan.append(([None,None,float(height)],40.,'z_up' if height==0 else 'z_down',1))
            for cycle in range(1,21):
                amplitude=.5*cycle
                other=height+amplitude if height+amplitude<=z else height-amplitude
                plan += [([None,None,other],40.,'z_repeat',cycle),
                         ([None,None,float(height)],40.,'z_repeat',cycle)]
        plan.append(([None,None,20.],40.,'z_finish',1))
        return plan
