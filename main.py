from __future__ import annotations

from dataclasses import dataclass
from typing import *

import re
import socket
import json

@dataclass(frozen=True)
class Robotarm:
    sock: socket.socket

    @staticmethod
    def init(host: str, port: int=23, password: str='Help') -> Robotarm:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
        res = Robotarm(sock)
        res.send('Help')
        res.wait_for_ready()
        return res

    def wait_for_ready(self):
        self.send('echo ready')
        self.recv_until('^ready')

    def recv_until(self, regex: str):
        data = ''
        while not re.search(regex, data, flags=re.MULTILINE):
            b = self.sock.recv(4096)
            data += b.decode(errors='replace')
        for line in data.splitlines():
            if line.startswith('log'):
                print(line)
            try:
                v = json.loads(line)
                print(v)
            except ValueError:
                pass
        # print(data, end='')
        return data

    def send(self, msg: str):
        msg += '\n'
        self.sock.sendall(msg.encode())

    def close(self):
        self.sock.close()

project = '''
ProjectBegin
ProjectName="imx_helper"
ProjectStart="Main"
ProjectSource="Main.gpl"
ProjectEnd
'''

module = '''
Module imx_helper
    Public Sub Main()
        Console.WriteLine("log Main()")
    End Sub
    Public Sub Run()
        Console.WriteLine("log Run")
        whereami()
    End Sub
    Public Sub demo()
        Robot.Attached = 1
        whereami()
        Up()
        whereami()
        Wiggle()
        Close()
        whereami()
        Down()
        whereami()
        Woggle()
        Open()
        whereami()
    End Sub
    Public Sub whereami()
        Console.WriteLine(fmt_pq())
    End Sub
    Public Sub MoveLin(ByVal x As Double, ByVal y As Double, ByVal z As Double, ByVal yaw As Double)
        Dim p As New Location
        Dim profile As New Profile
        p.XYZ(x, y, z, yaw, 90, -180)
        profile.Straight = True
        Move.Loc(p, profile)
        Console.WriteLine("log moving")
        Move.WaitForEOM
        Console.WriteLine("log done")
    End Sub
    Public Sub MoveJoint(ByVal q1 As Double, ByVal q2 As Double, ByVal q3 As Double, ByVal q4 As Double, ByVal q5 As Double)
        Dim q As New Location
        Dim profile As New Profile
        q.Angles(q1, q2, q3, q4, q5)
        profile.Straight = False
        Move.Loc(q, profile)
        Console.WriteLine("log moving")
        Move.WaitForEOM
        Console.WriteLine("log done")
    End Sub
    Public Sub Down()
        Dim p As Location
        p = Robot.Where()
        MoveLin(p.X, p.Y, p.Z - 30, p.Yaw)
    End Sub
    Public Sub Up()
        Dim p As Location
        p = Robot.Where()
        MoveLin(p.X, p.Y, p.Z + 30, p.Yaw)
    End Sub
    Public Sub Wiggle()
        Dim q As Location
        q = Robot.WhereAngles()
        MoveJoint(q.Angle(1), q.Angle(2) - 5, q.Angle(3), q.Angle(4), q.Angle(5))
    End Sub
    Public Sub Woggle()
        Dim q As Location
        q = Robot.WhereAngles()
        MoveJoint(q.Angle(1), q.Angle(2) + 5, q.Angle(3), q.Angle(4), q.Angle(5))
    End Sub
    Public Sub Close()
        Dim q As Location
        q = Robot.WhereAngles()
        MoveJoint(q.Angle(1), q.Angle(2), q.Angle(3), q.Angle(4), 110)
    End Sub
    Public Sub Open()
        Dim q As Location
        q = Robot.WhereAngles()
        MoveJoint(q.Angle(1), q.Angle(2), q.Angle(3), q.Angle(4), 126)
    End Sub
    Public Function fmt_pq() As String
        Dim p As Location
        Dim q As Location
        Dim msg As String
        p = Robot.Where()
        q = Robot.WhereAngles()
        msg = "{"
        msg = msg & q("x")     & fmt(p.X,        2) & ","
        msg = msg & q("y")     & fmt(p.Y,        2) & ","
        msg = msg & q("z")     & fmt(p.Z,        2) & ","
        msg = msg & q("yaw")   & fmt(p.Yaw,      2) & ","
        ' msg = msg & q("pitch") & fmt(p.Pitch,    2) & ","
        ' msg = msg & q("roll")  & fmt(p.Roll,     2) & ","
        msg = msg & q("q1")    & fmt(q.Angle(1), 2) & ","
        msg = msg & q("q2")    & fmt(q.Angle(2), 2) & ","
        msg = msg & q("q3")    & fmt(q.Angle(3), 2) & ","
        msg = msg & q("q4")    & fmt(q.Angle(4), 2) & ","
        msg = msg & q("q5")    & fmt(q.Angle(5), 2)
        msg = msg & "}"
        Return msg
    End Function
    Public Function round(ByVal value As Double, ByVal num_digits As Integer) As Double
        Dim scale As Double
        scale = Math.Pow(10, num_digits)
        Return Math.Floor(value * scale + 0.5) / scale
    End Function
    Public Function fmt(ByVal value As Double, ByVal num_digits As Integer) As String
        Return CStr(round(value, num_digits))
    End Function
    Public Function q(ByVal key As String) As String
        Return """" & key & """:"
    End Function
End Module
'''

def main():
    arm = Robotarm.init('10.10.0.98')
    end_of_text = '\u0003'
    arm.send('execute File.CreateDirectory("/flash/projects/imx_helper")')
    arm.send('create /flash/projects/imx_helper/Project.gpr' + '\n' + project.strip() + '\n' + end_of_text)
    arm.send('create /flash/projects/imx_helper/Main.gpl' + '\n' + module.strip() + '\n' + end_of_text)
    arm.send('unload -all')
    arm.send('load /flash/projects/imx_helper -compile')
    arm.send('execute Run()')
    arm.send('execute Console.WriteLine("log bye bye")')
    arm.send('quit')
    arm.recv_until('^Exiting console task')

if __name__ == '__main__':
    main()

