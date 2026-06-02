using ITPDroneGUI.Components;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddRazorComponents()
    .AddInteractiveServerComponents();

builder.Services.AddHttpClient<DroneApiService>();
builder.Services.AddSingleton<ProcedureStorageService>();

builder.Services.AddScoped(sp =>
    new HttpClient { BaseAddress = new Uri("http://127.0.0.1:8000") }
);

builder.Services.AddHttpsRedirection(options =>
{
    options.HttpsPort = 5001; 
});


var app = builder.Build();

if (!app.Environment.IsDevelopment())
{
    app.UseExceptionHandler("/Error", createScopeForErrors: true);
    app.UseHsts();
}


app.UseAntiforgery();
app.MapStaticAssets();
app.MapRazorComponents<App>()
    .AddInteractiveServerRenderMode();

app.Run();
