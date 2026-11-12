// Model injection boundary: cancellation is an empty native generation, never a
// detached rejected History summarization promise or a late physical command.
export class SessionModel {
  constructor(session, activity=()=>{}) {this.session=session;this.activity=activity;}
  async sendRequest(...args) {
    const {model,token}=this.session();
    if(!model || token?.cancelled)return '';
    this.activity();
    try {
      const result=await model.sendRequest(...args);
      return token?.cancelled || this.session().model!==model ? '' : result;
    }
    catch(error) {
      if(token?.cancelled || this.session().model!==model)return '';
      throw error;
    }
  }
}
