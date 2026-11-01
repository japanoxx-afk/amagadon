using System;using System.Linq;using System.Drawing;using System.Windows.Forms;
namespace Amagadon {
 public static class Hotkeys {
  public static int[][] Profiles;
  static readonly string[] Names=("Esc|1|2|3|4|5|6|7|8|9|0|-|=|Backspace|Tab|Q|W|E|R|T|Y|U|I|O|P|[|]|Enter|Ctrl|A|S|D|F|G|H|J|K|L|;|'|`|Shift|\\|Z|X|C|V|B|N|M|,|.|/|Right Shift|Num *|Alt|Space|Caps Lock|F1|F2|F3|F4|F5|F6|F7|F8|F9|F10").Split('|');
  public static byte[] RuntimeTable(){var table=new byte[1024];if(Profiles==null)return table;for(int p=0;p<Math.Min(4,Profiles.Length);p++)if(Profiles[p]!=null)for(int i=0;i<Math.Min(256,Profiles[p].Length);i++){int v=Profiles[p][i];if(v>0&&v<=Names.Length)table[p*256+i]=(byte)v;}return table;}
  public static void Edit(IWin32Window owner,Settings settings){
   int[][] maps=Enumerable.Range(0,4).Select(p=>settings.HotkeyProfiles!=null&&p<settings.HotkeyProfiles.Length&&settings.HotkeyProfiles[p]!=null?(int[])settings.HotkeyProfiles[p].Clone():new int[256]).ToArray();
   using(var f=new Form{Text="핫키 설정",ClientSize=new Size(640,640),StartPosition=FormStartPosition.CenterParent}){
    var profile=new ComboBox{Left=16,Top=16,Width=220,DropDownStyle=ComboBoxStyle.DropDownList};profile.Items.AddRange(new object[]{"공통","지구연합 · Earth","엘카 · Elca","이드 · EAD"});
    var description=new Label{Left=16,Top=52,Width=610,Height=48,Text="누를 키에 대응할 원래 키를 지정합니다. 진영 설정은 공통 설정보다 우선합니다.\r\n게임 화면에서 적용되며, 다음 게임 실행 시 반영됩니다."};
    var grid=new DataGridView{Left=16,Top=106,Width=608,Height=470,AllowUserToAddRows=false,AllowUserToDeleteRows=false,RowHeadersVisible=false,AutoSizeColumnsMode=DataGridViewAutoSizeColumnsMode.Fill};grid.Columns.Add(new DataGridViewTextBoxColumn{Name="input",HeaderText="누를 키",ReadOnly=true});var col=new DataGridViewComboBoxColumn{Name="target",HeaderText="실행할 원래 키"};col.Items.Add("기본 / 공통 설정 사용");col.Items.AddRange(Names.Cast<object>().ToArray());grid.Columns.Add(col);
    int current=-1;Action store=()=>{grid.EndEdit();if(current<0)return;for(int i=0;i<Names.Length;i++){string v=Convert.ToString(grid.Rows[i].Cells[1].Value);maps[current][i]=Array.IndexOf(Names,v)+1;}};
    profile.SelectedIndexChanged+=delegate{store();current=profile.SelectedIndex;grid.Rows.Clear();for(int i=0;i<Names.Length;i++){int v=maps[current][i];grid.Rows.Add(Names[i],v>0&&v<=Names.Length?Names[v-1]:"기본 / 공통 설정 사용");}};
    var save=new Button{Text="저장",Left=426,Top=590,Width=94};save.Click+=delegate{store();settings.HotkeyProfiles=maps;Profiles=maps;f.DialogResult=DialogResult.OK;f.Close();};var reset=new Button{Text="현재 진영 초기화",Left=16,Top=590,Width=160};reset.Click+=delegate{for(int i=0;i<grid.Rows.Count;i++)grid.Rows[i].Cells[1].Value="기본 / 공통 설정 사용";};var cancel=new Button{Text="취소",Left=530,Top=590,Width=94,DialogResult=DialogResult.Cancel};f.Controls.AddRange(new Control[]{profile,description,grid,save,reset,cancel});profile.SelectedIndex=0;f.ShowDialog(owner);
   }
  }
 }
}
