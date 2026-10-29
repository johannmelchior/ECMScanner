namespace BUDS2
{
	// Token: 0x02000009 RID: 9
	[global::Microsoft.VisualBasic.CompilerServices.DesignerGenerated]
	public partial class buds2 : global::System.Windows.Forms.Form
	{
		// Token: 0x06000033 RID: 51 RVA: 0x00002E78 File Offset: 0x00001078
		[global::System.Diagnostics.DebuggerNonUserCode]
		protected override void Dispose(bool disposing)
		{
			try
			{
				if (disposing && this.components != null)
				{
					this.components.Dispose();
				}
			}
			finally
			{
				base.Dispose(disposing);
			}
		}

		// Token: 0x06000034 RID: 52 RVA: 0x00002EB8 File Offset: 0x000010B8
		[global::System.Diagnostics.DebuggerStepThrough]
		private void InitializeComponent()
		{
			global::System.ComponentModel.ComponentResourceManager componentResourceManager = new global::System.ComponentModel.ComponentResourceManager(typeof(global::BUDS2.buds2));
			this.lblEmail = new global::System.Windows.Forms.Label();
			this.txtName = new global::System.Windows.Forms.TextBox();
			this.lblName = new global::System.Windows.Forms.Label();
			this.txtSurname = new global::System.Windows.Forms.TextBox();
			this.lblSurname = new global::System.Windows.Forms.Label();
			this.txtCompany = new global::System.Windows.Forms.TextBox();
			this.lblCompany = new global::System.Windows.Forms.Label();
			this.txtPhone = new global::System.Windows.Forms.TextBox();
			this.lblPhone = new global::System.Windows.Forms.Label();
			this.btnGetLicense = new global::System.Windows.Forms.Button();
			this.txtEmail = new global::System.Windows.Forms.TextBox();
			this.cmbLang = new global::System.Windows.Forms.ComboBox();
			this.Label1 = new global::System.Windows.Forms.Label();
			base.SuspendLayout();
			this.lblEmail.AutoSize = true;
			this.lblEmail.Location = new global::System.Drawing.Point(12, 9);
			this.lblEmail.Name = "lblEmail";
			this.lblEmail.Size = new global::System.Drawing.Size(59, 13);
			this.lblEmail.TabIndex = 0;
			this.lblEmail.Text = "User email:";
			this.txtName.Location = new global::System.Drawing.Point(77, 32);
			this.txtName.Name = "txtName";
			this.txtName.Size = new global::System.Drawing.Size(195, 20);
			this.txtName.TabIndex = 3;
			this.lblName.AutoSize = true;
			this.lblName.Location = new global::System.Drawing.Point(12, 35);
			this.lblName.Name = "lblName";
			this.lblName.Size = new global::System.Drawing.Size(38, 13);
			this.lblName.TabIndex = 2;
			this.lblName.Text = "Name:";
			this.txtSurname.Location = new global::System.Drawing.Point(77, 58);
			this.txtSurname.Name = "txtSurname";
			this.txtSurname.Size = new global::System.Drawing.Size(195, 20);
			this.txtSurname.TabIndex = 5;
			this.lblSurname.AutoSize = true;
			this.lblSurname.Location = new global::System.Drawing.Point(12, 61);
			this.lblSurname.Name = "lblSurname";
			this.lblSurname.Size = new global::System.Drawing.Size(52, 13);
			this.lblSurname.TabIndex = 4;
			this.lblSurname.Text = "Surname:";
			this.txtCompany.Location = new global::System.Drawing.Point(77, 84);
			this.txtCompany.Name = "txtCompany";
			this.txtCompany.Size = new global::System.Drawing.Size(195, 20);
			this.txtCompany.TabIndex = 7;
			this.lblCompany.AutoSize = true;
			this.lblCompany.Location = new global::System.Drawing.Point(12, 87);
			this.lblCompany.Name = "lblCompany";
			this.lblCompany.Size = new global::System.Drawing.Size(54, 13);
			this.lblCompany.TabIndex = 6;
			this.lblCompany.Text = "Company:";
			this.txtPhone.Location = new global::System.Drawing.Point(77, 110);
			this.txtPhone.Name = "txtPhone";
			this.txtPhone.Size = new global::System.Drawing.Size(195, 20);
			this.txtPhone.TabIndex = 9;
			this.lblPhone.AutoSize = true;
			this.lblPhone.Location = new global::System.Drawing.Point(12, 113);
			this.lblPhone.Name = "lblPhone";
			this.lblPhone.Size = new global::System.Drawing.Size(41, 13);
			this.lblPhone.TabIndex = 8;
			this.lblPhone.Text = "Phone:";
			this.btnGetLicense.Location = new global::System.Drawing.Point(15, 161);
			this.btnGetLicense.Name = "btnGetLicense";
			this.btnGetLicense.Size = new global::System.Drawing.Size(257, 23);
			this.btnGetLicense.TabIndex = 10;
			this.btnGetLicense.Text = "Get License";
			this.btnGetLicense.UseVisualStyleBackColor = true;
			this.txtEmail.Location = new global::System.Drawing.Point(77, 6);
			this.txtEmail.Name = "txtEmail";
			this.txtEmail.Size = new global::System.Drawing.Size(195, 20);
			this.txtEmail.TabIndex = 1;
			this.cmbLang.FormattingEnabled = true;
			this.cmbLang.Items.AddRange(new object[]
			{
				"en", "de", "es", "fi", "fr", "it", "ja", "no", "pt", "ru",
				"sv", "zh"
			});
			this.cmbLang.Location = new global::System.Drawing.Point(77, 137);
			this.cmbLang.Name = "cmbLang";
			this.cmbLang.Size = new global::System.Drawing.Size(195, 21);
			this.cmbLang.TabIndex = 11;
			this.Label1.AutoSize = true;
			this.Label1.Location = new global::System.Drawing.Point(12, 140);
			this.Label1.Name = "Label1";
			this.Label1.Size = new global::System.Drawing.Size(58, 13);
			this.Label1.TabIndex = 12;
			this.Label1.Text = "Language:";
			base.AutoScaleDimensions = new global::System.Drawing.SizeF(6f, 13f);
			base.AutoScaleMode = global::System.Windows.Forms.AutoScaleMode.Font;
			base.ClientSize = new global::System.Drawing.Size(284, 196);
			base.Controls.Add(this.Label1);
			base.Controls.Add(this.cmbLang);
			base.Controls.Add(this.btnGetLicense);
			base.Controls.Add(this.txtPhone);
			base.Controls.Add(this.lblPhone);
			base.Controls.Add(this.txtCompany);
			base.Controls.Add(this.lblCompany);
			base.Controls.Add(this.txtSurname);
			base.Controls.Add(this.lblSurname);
			base.Controls.Add(this.txtName);
			base.Controls.Add(this.lblName);
			base.Controls.Add(this.txtEmail);
			base.Controls.Add(this.lblEmail);
			base.Icon = (global::System.Drawing.Icon)componentResourceManager.GetObject("$this.Icon");
			base.Name = "Form1";
			base.StartPosition = global::System.Windows.Forms.FormStartPosition.CenterScreen;
			this.Text = "BUDS2 License Registrator";
			base.ResumeLayout(false);
			base.PerformLayout();
		}

		// Token: 0x0400001D RID: 29
		private global::System.ComponentModel.IContainer components;
	}
}
