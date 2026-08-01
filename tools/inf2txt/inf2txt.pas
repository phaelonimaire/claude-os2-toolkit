program inf2txt;
{$mode objfpc}{$H+}
uses Classes, SysUtils, HelpFile, HelpTopic;
var hf: THelpFile; t: TTopic; i: longint; s: string; imgs: TList;
begin
  if ParamCount<1 then begin writeln(stderr,'usage: inf2txt <inf>'); halt(1); end;
  hf := THelpFile.Create(ParamStr(1));
  try
    for i := 0 to hf.TopicCount-1 do begin
      t := hf.Topics[i];
      writeln('=== ', t.Title, ' ===');
      imgs := TList.Create;
      try s:=''; t.GetText(nil,false,false,s,imgs,nil); writeln(s);
      finally imgs.Free; end;
      writeln;
    end;
  finally hf.Free; end;
end.
